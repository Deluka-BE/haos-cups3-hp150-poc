"""No jobs: exact-source transformation and executable sanitized metadata probes."""
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('boundaries', ROOT / 'scripts/patch-pappl-lifecycle.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class BoundaryTests(unittest.TestCase):
    def fixture(self, root):
        shutil.copytree(ROOT / 'tests/fixtures/lifecycle/pappl', root / 'pappl')

    def test_every_anchor_fails_closed_missing_and_duplicate(self):
        for name, rules in patcher.RULES.items():
            # Drift at every sequential anchor, including anchors produced by earlier rules.
            for index, (anchor, _) in enumerate(rules):
                for duplicate in (False, True):
                    with self.subTest(name=name, index=index, duplicate=duplicate), tempfile.TemporaryDirectory() as tmp:
                        root = Path(tmp)
                        self.fixture(root)
                        path = root / 'pappl' / name
                        text = path.read_text()
                        for old, new in rules[:index]:
                            self.assertEqual(text.count(old), 1)
                            text = text.replace(old, new)
                        self.assertEqual(text.count(anchor), 1)
                        path.write_text(text + '\n' + anchor if duplicate else text.replace(anchor, '/* drift */'))
                        before = {p: p.read_bytes() for p in (root / 'pappl').iterdir()}
                        remaining = dict(patcher.RULES, **{name: rules[index:]})
                        with patch.object(patcher, 'RULES', remaining), self.assertRaises(ValueError):
                            patcher.patch(root)
                        self.assertEqual(before, {p: p.read_bytes() for p in (root / 'pappl').iterdir()})

    def test_additive_transform_preserves_baseline_calls_and_cancellation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            baseline = {}
            for name, rules in patcher.RULES.items():
                text = (root / 'pappl' / name).read_text()
                original_rules = rules[:-len(patcher.EXTRA[name])] if name in patcher.EXTRA else rules
                for old, new in original_rules:
                    text = text.replace(old, new)
                baseline[name] = text
            patcher.patch(root)
            for name, expected in baseline.items():
                text = (root / 'pappl' / name).read_text()
                for old, new in reversed(patcher.EXTRA.get(name, [])):
                    self.assertEqual(text.count(new), 1)
                    text = text.replace(new, old)
                self.assertEqual(text, expected)
            combined = '\n'.join(new for rules in patcher.EXTRA.values() for _, new in rules)
            for forbidden in ('sleep(', 'pthread_create(', 'papplJobCreate(', 'papplPrinterCreate(', 'httpWrite(', 'cupsRasterReadPixels('):
                self.assertNotIn(forbidden, combined)
            self.assertIn('poc_present = httpPeek(client->http, &temp, 1) > 0;', combined)
            self.assertIn('errno = poc_errno;', combined)

    def test_processing_order_and_error_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            patcher.patch(root)
            text = (root / 'pappl/job-process.c').read_text()
            start = text.index('job->streaming = true;')
            markers = ['raster-open begin', 'cupsRasterOpenIO', 'raster-open result=error',
                       'raster-open result=success', 'raster-first-header begin', 'cupsRasterReadHeader',
                       'raster-first-header result=error', 'raster-first-header result=success',
                       'print-options begin mode=streaming', 'papplJobCreatePrintOptions',
                       'print-options result=%d mode=streaming', 'print-dispatch begin callback=rstartjob',
                       'rstartjob_cb', 'print-dispatch returned callback=rstartjob result=0',
                       'print-dispatch returned callback=rstartjob result=1']
            positions = [text.index(marker, start) for marker in markers]
            self.assertEqual(positions, sorted(positions))
            self.assertLess(text.index('processing-set'), text.index('device-availability begin'))
            self.assertLess(text.index('device-availability result'), text.index('device-open begin'))
            receipt = (root / 'pappl/job-ipp.c').read_text()
            markers = ['document-receive result=', 'spool-close begin', 'close(job->fd)',
                       'spool-close result=error', 'spool-close result=success', 'spool-submit begin',
                       '_papplJobSubmitFile', 'spool-submit returned']
            pos = receipt.index('document-receive result=')
            positions = [receipt.index(marker, pos) for marker in markers]
            self.assertEqual(positions, sorted(positions))

    def test_cancellation_guards_and_cleanup_order_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            patcher.patch(root)
            text = (root / 'pappl/job-process.c').read_text()
            self.assertLess(text.index('if (!start_job(job))'), text.index('raster-open begin'))
            self.assertIn('if (!start_job(job))\n    goto complete_job;', text)
            self.assertIn('while (printer->device_in_use && !printer->is_deleted && !job->is_canceled && papplSystemIsRunning(printer->system))', text)
            self.assertIn('while (!printer->device && !printer->is_deleted && !job->is_canceled && papplSystemIsRunning(printer->system))', text)
            self.assertLess(text.index('if (job->is_canceled)'), text.index('page ++;'))
            self.assertLess(text.index('document-stream complete'), text.index('finish_job(job);'))

    def test_new_log_arguments_are_redacted(self):
        text = patcher.HEADER + '\n'.join(new for rules in patcher.EXTRA.values() for _, new in rules)
        logs = re.findall(r'POC_INFO\([^;]+;', text)
        self.assertGreater(len(logs), 20)
        for log in logs:
            for forbidden in ('->name', '->username', '->device_uri', 'filename', 'strerror', 'httpGetField', '%p', '%llu'):
                self.assertNotIn(forbidden, log)
            self.assertNotIn('papplLogClient', log)
        self.assertIn('errno = poc_saved_errno', patcher.HEADER)
        self.assertNotIn('httpRead', patcher.HEADER)
        self.assertNotIn('httpPeek', patcher.HEADER)

    @unittest.skipUnless(shutil.which('cc'), 'C compiler required for metadata probe')
    def test_executable_metadata_partial_error_and_operation_paths(self):
        stub = r'''
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <assert.h>
#include <errno.h>
typedef int ipp_op_t;
#define IPP_OP_PRINT_JOB 2
#define IPP_OP_CREATE_JOB 5
#define IPP_OP_SEND_DOCUMENT 6
#define IPP_TAG_ZERO 0
#define IPP_TAG_MIMETYPE 1
#define IPP_TAG_KEYWORD 2
#define IPP_TAG_OPERATION 3
#define IPP_TAG_BOOLEAN 4
#define IPP_TAG_INTEGER 5
#define PAPPL_LOGLEVEL_INFO 1
typedef struct { const char *value; int group, tag, count, boolean; } ipp_attribute_t;
typedef struct { int op, id, status, job; ipp_attribute_t *format, *compression, *last; } ipp_t;
typedef struct { ipp_t *request, *response; void *system; void *http; } pappl_client_t;
static ipp_op_t ippGetOperation(ipp_t *i) { return i->op; }
static int ippGetRequestId(ipp_t *i) { return i->id; }
static int ippGetStatusCode(ipp_t *i) { return i->status; }
static ipp_attribute_t *ippFindAttribute(ipp_t *i, const char *name, int tag) {
 ipp_attribute_t *a = !strcmp(name,"document-format") ? i->format : !strcmp(name,"compression") ? i->compression : !strcmp(name,"last-document") ? i->last : NULL;
 return a && (!tag || a->tag == tag) ? a : NULL;
}
static const char *ippGetString(ipp_attribute_t *a, int i, void *p) { return a ? a->value : NULL; }
static int ippGetInteger(ipp_attribute_t *a, int i) { return 0; }
static int ippGetGroupTag(ipp_attribute_t *a) { return a->group; }
static int ippGetValueTag(ipp_attribute_t *a) { return a->tag; }
static int ippGetCount(ipp_attribute_t *a) { return a->count; }
static int ippGetBoolean(ipp_attribute_t *a, int i) { return a->boolean; }
static char output[8192];
static void papplLog(void *o, int level, const char *fmt, ...) {
 va_list ap; va_start(ap,fmt); vsnprintf(output+strlen(output),sizeof(output)-strlen(output),fmt,ap); va_end(ap); errno=EIO;
}
'''
        presence = '''bool observed_presence(pappl_client_t *client)
{
  char temp;\t\t\t\t// Data
  if (httpGetState(client->http) != HTTP_STATE_POST_RECV)
    return (false);
  else
    return (httpPeek(client->http, &temp, 1) > 0);
}
'''
        for old, new in patcher.EXTRA['client-ipp.c']:
            if old in presence:
                presence = presence.replace(old, new)
        stub += '''
#define HTTP_STATE_POST_RECV 1
static int http_state=1, peek_value, peek_calls;
static int httpGetState(void *http) { return http_state; }
static int httpPeek(void *http, char *buffer, int count) { peek_calls++; errno=EPIPE; return peek_value; }
'''
        main = r'''
int main(void) {
 const char *mime[] = {"application/pdf","image/urf","image/pwg-raster","image/jpeg","image/png","application/postscript","application/octet-stream","secret",NULL};
 const char *label[] = {"pdf","urf","pwg-raster","jpeg","png","postscript","octet-stream","other","unknown"};
 const char *comp[] = {"none","gzip","deflate","compress","secret",NULL};
 const char *clabel[] = {"none","gzip","deflate","compress","other","unknown"};
 for(int i=0;i<9;i++) assert(!strcmp(pocFormat(mime[i]),label[i]));
 for(int i=0;i<6;i++) assert(!strcmp(pocCompression(comp[i]),clabel[i]));
 ipp_attribute_t f={"secret",3,1,1,0}, c={"secret",3,2,1,0}, l={NULL,3,4,1,1};
 ipp_t req={2,9,0,0,&f,&c,NULL}, res={0,0,0,0,NULL,NULL,NULL};
 pappl_client_t client={&req,&res,NULL};
 for(int op=2;op<=6;op++) {
  req.op=op; output[0]=0; errno=ERANGE; pocRequest(&client); pocResponse(&client); assert(errno==ERANGE); assert(!strstr(output,"secret"));
  if(op==2 || op==5 || op==6) { assert(strstr(output,"begin request=9")); assert(strstr(output,"status=success")); }
  else assert(!output[0]);
  if(op!=6) assert(!strstr(output,"last-document"));
 }
 req.op=6;
 for(int i=-1;i<=1;i++) { peek_calls=0; peek_value=i; errno=ERANGE; output[0]=0; assert(observed_presence(&client)==(i>0)); assert(peek_calls==1); assert(errno==EPIPE); }
 http_state=0; peek_calls=0; errno=ERANGE; assert(!observed_presence(&client)); assert(peek_calls==0); assert(errno==ERANGE);
 output[0]=0; pocRequest(&client); assert(strstr(output,"present=0 valid=0 value=0"));
 req.last=&l;
 for(int b=0;b<2;b++) { l.boolean=b; output[0]=0; pocRequest(&client); assert(strstr(output,b ? "present=1 valid=1 value=1" : "present=1 valid=1 value=0")); }
 for(int i=0;i<3;i++) { l.group=i==0?0:3; l.tag=i==1?2:4; l.count=i==2?2:1; output[0]=0; pocRequest(&client); assert(strstr(output,"present=1 valid=0 value=0")); }
 req.id=-1; res.status=0x0400; output[0]=0; pocResponse(&client); assert(strstr(output,"request=0")); assert(strstr(output,"status=client-error"));
 res.status=0x0500; output[0]=0; pocResponse(&client); assert(strstr(output,"status=server-error"));
 return 0;
}
'''
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            source = Path(tmp) / 'probe.c'
            source.write_text(stub + patcher.HEADER + presence + main)
            subprocess.run(['cc', '-std=c99', str(source), '-o', str(Path(tmp) / 'probe')], check=True, capture_output=True)
            subprocess.run([str(Path(tmp) / 'probe')], check=True)
