#!/usr/bin/env python3
"""Diagnostics only, fail closed before writing any file if PAPPL 1.3.1 anchors drift."""
from pathlib import Path
import sys

# Reviewed against Debian pappl_1.3.1.orig.tar.gz. All values are numeric or fixed enums.
RULES = {'client-ipp.c': [('  op    = ippGetOperation(client->request);',
                   '  op    = ippGetOperation(client->request);\n'
                   '  if (op == IPP_OP_PRINT_JOB || op == IPP_OP_CREATE_JOB || op == IPP_OP_SEND_DOCUMENT)\n'
                   '    papplLog(client->system, PAPPL_LOGLEVEL_INFO, "lifecycle stage=ipp-decoded '
                   'operation=%d", (int)op);')],
 'job.c': [('  if (printer->max_active_jobs > 0 && (int)cupsArrayGetCount(printer->active_jobs) >= '
            'printer->max_active_jobs)',
            '  papplLog(printer->system, PAPPL_LOGLEVEL_INFO, "lifecycle stage=job-create begin queue=%d", '
            'printer->printer_id);\n'
            '  if (printer->max_active_jobs > 0 && (int)cupsArrayGetCount(printer->active_jobs) >= '
            'printer->max_active_jobs)'),
           ('  if (printer->max_active_jobs > 0 && (int)cupsArrayGetCount(printer->active_jobs) >= '
            'printer->max_active_jobs)\n'
            '  {',
            '  if (printer->max_active_jobs > 0 && (int)cupsArrayGetCount(printer->active_jobs) >= '
            'printer->max_active_jobs)\n'
            '  {\n'
            '    papplLog(printer->system, PAPPL_LOGLEVEL_INFO, "lifecycle stage=job-create result=0 '
            'reason=capacity queue=%d", printer->printer_id);'),
           ('    papplLog(printer->system, PAPPL_LOGLEVEL_ERROR, "Unable to allocate memory for job: %s", '
            'strerror(errno));',
            '    papplLog(printer->system, PAPPL_LOGLEVEL_ERROR, "Unable to allocate memory for job: %s", '
            'strerror(errno));\n'
            '    papplLog(printer->system, PAPPL_LOGLEVEL_INFO, "lifecycle stage=job-create result=0 '
            'reason=allocation queue=%d", printer->printer_id);'),
           ('  cupsArrayAdd(printer->all_jobs, job);',
            '  cupsArrayAdd(printer->all_jobs, job);\n'
            '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=job-create result=1 queue=%d state=%d '
            'reasons=%u", printer->printer_id, (int)job->state, (unsigned)job->state_reasons);'),
           ('      job->state = IPP_JSTATE_PENDING;\n      _papplPrinterCheckJobs(job->printer);',
            '      job->state = IPP_JSTATE_PENDING;\n'
            '      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=registered state=%d reasons=%u '
            'reason=ready", (int)job->state, (unsigned)job->state_reasons);\n'
            '      _papplPrinterCheckJobs(job->printer);'),
           ('      _papplPrinterCheckJobs(job->printer);',
            '      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=scheduler-check reason=%s", '
            'job->printer->device_in_use ? "device-in-use" : job->printer->processing_job ? "processing" : '
            'job->printer->is_deleted ? "deleted" : (job->printer->state == IPP_PSTATE_STOPPED || '
            'job->printer->is_stopped) ? "stopped" : "check");\n'
            '      _papplPrinterCheckJobs(job->printer);'),
           ('      _papplPrinterCheckJobs(job->printer);\n    }\n  }\n  else',
            '      _papplPrinterCheckJobs(job->printer);\n'
            '    }\n'
            '    else\n'
            '      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=registered state=%d reasons=%u '
            'reason=%s", (int)job->state, (unsigned)job->state_reasons, job->printer->hold_new_jobs ? '
            '"hold-new" : "hold-until");\n'
            '  }\n'
            '  else'),
           ('      papplLogPrinter(printer, PAPPL_LOGLEVEL_DEBUG, "Starting job %d.", job->job_id);',
            '      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=scheduler-launch begin");\n'
            '      papplLogPrinter(printer, PAPPL_LOGLEVEL_DEBUG, "Starting job %d.", job->job_id);'),
           ('\tjob->state     = IPP_JSTATE_ABORTED;\n\tjob->completed = time(NULL);',
            '        papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=scheduler-launch result=0 '
            'reason=thread-create");\n'
            '\tjob->state     = IPP_JSTATE_ABORTED;\n'
            '\tjob->completed = time(NULL);'),
           ('      else\n\tpthread_detach(t);',
            '      else\n'
            '      {\n'
            '        papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=scheduler-launch result=1");\n'
            '\tpthread_detach(t);\n'
            '      }')],
 'job-ipp.c': [('  // If we have a PWG or Apple raster file, process it directly or return',
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=document-receipt begin");\n'
                '  // If we have a PWG or Apple raster file, process it directly or return'),
               ('    _papplJobProcessRaster(job, client);',
                '    papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=registered state=%d '
                'reason=streaming-ready", (int)job->state);\n'
                '    _papplJobProcessRaster(job, client);'),
               ('  while ((bytes = httpRead(client->http, buffer, sizeof(buffer))) > 0)',
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=document-spool begin");\n'
                '  while ((bytes = httpRead(client->http, buffer, sizeof(buffer))) > 0)'),
               ('    total += (size_t)bytes;',
                '    if (!total)\n'
                '      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=document-spool first-write '
                'bytes=%llu", (unsigned long long)bytes);\n'
                '    total += (size_t)bytes;'),
               ('  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "Received %lu bytes of document data.", (unsigned '
                'long)total);',
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=document-spool complete '
                'bytes=%llu", (unsigned long long)total);\n'
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "Received %lu bytes of document data.", (unsigned '
                'long)total);'),
               ('      papplClientRespondIPP(client, IPP_STATUS_ERROR_BUSY, "Currently printing another '
                'job.");',
                '      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=document-receipt rejected '
                'reason=processing");\n'
                '      papplClientRespondIPP(client, IPP_STATUS_ERROR_BUSY, "Currently printing another '
                'job.");'),
               ('      papplClientRespondIPP(client, IPP_STATUS_ERROR_NOT_ACCEPTING_JOBS, "Currently holding '
                'new jobs.");',
                '      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=document-receipt rejected '
                'reason=hold-new");\n'
                '      papplClientRespondIPP(client, IPP_STATUS_ERROR_NOT_ACCEPTING_JOBS, "Currently holding '
                'new jobs.");'),
               ('  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "Aborting job.");',
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=document-receipt aborted");\n'
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "Aborting job.");')],
 'job-process.c': [('  // Start processing the job...\n  if (start_job(job))',
                    '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=execution mode=spooled");\n'
                    '  // Start processing the job...\n'
                    '  if (start_job(job))'),
                   ('  job->streaming = true;',
                    '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=execution mode=streaming");\n'
                    '  job->streaming = true;'),
                   ('    papplLogJob(job, PAPPL_LOGLEVEL_DEBUG, "Waiting for device to become available.");',
                    '    papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=device-wait begin '
                    'reason=device-in-use");\n'
                    '    papplLogJob(job, PAPPL_LOGLEVEL_DEBUG, "Waiting for device to become available.");'),
                   ('    printer->device = papplDeviceOpen(printer->device_uri, job->name, papplLogDevice, '
                    'job->system);',
                    '    if (first_open)\n'
                    '      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=device-open begin");\n'
                    '    printer->device = papplDeviceOpen(printer->device_uri, job->name, papplLogDevice, '
                    'job->system);'),
                   ('    printer->device = papplDeviceOpen(printer->device_uri, job->name, papplLogDevice, '
                    'job->system);',
                    '    printer->device = papplDeviceOpen(printer->device_uri, job->name, papplLogDevice, '
                    'job->system);\n'
                    '    if (first_open)\n'
                    '      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=device-open result=%d", '
                    'printer->device != NULL);'),
                   ('  return (printer->device != NULL);',
                    '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=device-ready result=%d '
                    'reason=%s", printer->device != NULL, printer->device ? "available" : '
                    'printer->is_deleted ? "deleted" : job->is_canceled ? "canceled" : "system-stopped");\n'
                    '  return (printer->device != NULL);'),
                   ('  finish_job(job);\n  return;',
                    '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=document-stream complete '
                    'state=%d", (int)job->state);\n'
                    '  finish_job(job);\n'
                    '  return;')]}


# 0.1.20: additive boundaries only; no extra reads, clocks, retries or callbacks.
HEADER = r"""/* Diagnostics only. All labels are literals; preserve errno across logging. */
#ifndef POC_BOUNDARIES_H
#define POC_BOUNDARIES_H
#include <errno.h>
#define POC_INFO(logger, object, ...) do { int poc_saved_errno = errno; \
  logger(object, PAPPL_LOGLEVEL_INFO, __VA_ARGS__); errno = poc_saved_errno; } while (0)
static inline const char *pocFormat(const char *value)
{
  if (!value) return "unknown";
  if (!strcmp(value, "application/pdf")) return "pdf";
  if (!strcmp(value, "image/urf")) return "urf";
  if (!strcmp(value, "image/pwg-raster")) return "pwg-raster";
  if (!strcmp(value, "image/jpeg")) return "jpeg";
  if (!strcmp(value, "image/png")) return "png";
  if (!strcmp(value, "application/postscript")) return "postscript";
  if (!strcmp(value, "application/octet-stream")) return "octet-stream";
  return "other";
}
static inline const char *pocCompression(const char *value)
{
  if (!value) return "unknown";
  if (!strcmp(value, "none")) return "none";
  if (!strcmp(value, "gzip")) return "gzip";
  if (!strcmp(value, "deflate")) return "deflate";
  if (!strcmp(value, "compress")) return "compress";
  return "other";
}
static inline bool pocSubmission(ipp_op_t op)
{
  return op == IPP_OP_PRINT_JOB || op == IPP_OP_CREATE_JOB || op == IPP_OP_SEND_DOCUMENT;
}
static inline int pocId(int value) { return value > 0 ? value : 0; }
static inline const char *pocOperation(ipp_op_t op)
{
  return op == IPP_OP_PRINT_JOB ? "print-job" : op == IPP_OP_CREATE_JOB ? "create-job" : "send-document";
}
static inline void pocRequest(pappl_client_t *client)
{
  ipp_op_t op = ippGetOperation(client->request);
  ipp_attribute_t *last;
  bool valid;
  int saved = errno;
  if (pocSubmission(op))
  {
    POC_INFO(papplLog, client->system, "lifecycle stage=ipp-submission begin request=%d operation=%s supplied=%s compression=%s",
      pocId(ippGetRequestId(client->request)), pocOperation(op),
      pocFormat(ippGetString(ippFindAttribute(client->request, "document-format", IPP_TAG_MIMETYPE), 0, NULL)),
      pocCompression(ippGetString(ippFindAttribute(client->request, "compression", IPP_TAG_KEYWORD), 0, NULL)));
    if (op == IPP_OP_SEND_DOCUMENT)
    {
      last = ippFindAttribute(client->request, "last-document", IPP_TAG_ZERO);
      valid = last && ippGetGroupTag(last) == IPP_TAG_OPERATION && ippGetValueTag(last) == IPP_TAG_BOOLEAN && ippGetCount(last) == 1;
      POC_INFO(papplLog, client->system, "lifecycle stage=ipp-last-document request=%d present=%d valid=%d value=%d",
        pocId(ippGetRequestId(client->request)), last != NULL, valid, valid ? !!ippGetBoolean(last, 0) : 0);
    }
  }
  errno = saved;
}
static inline void pocResponse(pappl_client_t *client)
{
  ipp_op_t op = ippGetOperation(client->request);
  int saved = errno;
  if (pocSubmission(op))
    POC_INFO(papplLog, client->system, "lifecycle stage=ipp-submission returned request=%d operation=%s job=%d status=%s",
      pocId(ippGetRequestId(client->request)), pocOperation(op),
      pocId(ippGetInteger(ippFindAttribute(client->response, "job-id", IPP_TAG_INTEGER), 0)),
      ippGetStatusCode(client->response) < 0x0100 ? "success" : ippGetStatusCode(client->response) < 0x0400 ? "other" : ippGetStatusCode(client->response) < 0x0500 ? "client-error" : "server-error");
  errno = saved;
}
#endif
"""

def info(stage, args='', obj='job'):
    logger = 'papplLogJob' if obj == 'job' else 'papplLog'
    return '  POC_INFO(' + logger + ', ' + obj + ', "lifecycle stage=' + stage + '"' + args + ');\n'

EXTRA = {name: [('#include "pappl-private.h"', '#include "pappl-private.h"\n#include "poc-boundaries.h"')]
         for name in ('client-ipp.c', 'job-ipp.c', 'job-process.c')}
def before(name, anchor, log):
    EXTRA[name].append((anchor, log + anchor))
def after(name, anchor, log):
    EXTRA[name].append((anchor, anchor + '\n' + log.rstrip('\n')))

after('client-ipp.c', '  op    = ippGetOperation(client->request);', '  pocRequest(client);\n')
before('client-ipp.c', '  // Send the HTTP header and return...', '  pocResponse(client);\n')
# Observe the existing presence probe exactly once, never add a peek/read.
EXTRA['client-ipp.c'].append(('  char temp;\t\t\t\t// Data', '  char temp;\t\t\t\t// Data\n  bool poc_present;\n  int poc_errno;'))
EXTRA['client-ipp.c'].append(('  else\n    return (httpPeek(client->http, &temp, 1) > 0);', """  else
  {
    if (pocSubmission(ippGetOperation(client->request)))
      POC_INFO(papplLog, client->system, "lifecycle stage=ipp-data begin request=%d", pocId(ippGetRequestId(client->request)));
    poc_present = httpPeek(client->http, &temp, 1) > 0;
    poc_errno = errno;
    if (pocSubmission(ippGetOperation(client->request)))
      POC_INFO(papplLog, client->system, "lifecycle stage=ipp-data result request=%d present=%d", pocId(ippGetRequestId(client->request)), poc_present);
    errno = poc_errno;
    return (poc_present);
  }"""))
EXTRA['client-ipp.c'].append(('  if (httpGetState(client->http) != HTTP_STATE_POST_RECV)\n    return (false);', """  if (httpGetState(client->http) != HTTP_STATE_POST_RECV)
  {
    if (pocSubmission(ippGetOperation(client->request)))
      POC_INFO(papplLog, client->system, "lifecycle stage=ipp-data result request=%d present=0", pocId(ippGetRequestId(client->request)));
    return (false);
  }"""))
before('job-ipp.c', '  // If we have a PWG or Apple raster file, process it directly or return', info('document-effective request=%d operation=%s format=%s', ', pocId(ippGetRequestId(client->request)), pocOperation(ippGetOperation(client->request)), pocFormat(job->format)'))
before('job-ipp.c', '  // Create a file for the request data...', info('document-branch mode=spooled-non-raster'))
before('job-ipp.c', '    _papplJobProcessRaster(job, client);', info('document-branch mode=streaming-raster'))
before('job-ipp.c', '  if (bytes < 0)', info('document-receive result=%s', ', bytes < 0 ? "error" : "eof"'))
before('job-ipp.c', '  if (close(job->fd))', info('spool-close begin'))
after('job-ipp.c', '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "Received %lu bytes of document data.", (unsigned long)total);', info('spool-close result=success'))
before('job-ipp.c', '  _papplJobSubmitFile(job, filename);', info('spool-submit begin'))
after('job-ipp.c', '  _papplJobSubmitFile(job, filename);', info('spool-submit returned'))
before('job-ipp.c', '    papplClientRespondIPP(client, IPP_STATUS_ERROR_INTERNAL, "Unable to write print file: %s", strerror(error));\n\n    goto abort_job;\n  }\n\n  papplLogJob', info('spool-close result=error'))
after('job-process.c', '  job->state              = IPP_JSTATE_PROCESSING;', info('processing-set'))
before('job-process.c', '  // Open the output device...', info('device-availability begin in-use=%d', ', printer->device_in_use'))
before('job-process.c', '  while (!printer->device && !printer->is_deleted && !job->is_canceled && papplSystemIsRunning(printer->system))', info('device-availability result=%s', ', printer->is_deleted ? "deleted" : job->is_canceled ? "canceled" : printer->device_in_use ? "unavailable" : "available"'))
before('job-process.c', '  // Open the raster stream...', info('raster-open begin'))
after('job-process.c', '  {\n    papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Unable to open raster stream from client - %s", cupsLastErrorString());', info('raster-open result=error'))
before('job-process.c', '  // Prepare options...', info('raster-open result=success') + info('raster-first-header begin'))
after('job-process.c', '  {\n    papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Unable to read raster stream from client - %s", cupsLastErrorString());', info('raster-first-header result=error'))
before('job-process.c', '  if ((header_pages = header.cupsInteger[CUPS_RASTER_PWG_TotalPageCount]) > 0)', info('raster-first-header result=success'))
anchor='\n  options = papplJobCreatePrintOptions(job, (unsigned)job->impressions, header.cupsBitsPerPixel > 8);'
before('job-process.c', anchor, info('print-options begin mode=streaming'))
after('job-process.c', anchor, info('print-options result=%d mode=streaming', ', options != NULL'))
# Preserve callback conditions and calls verbatim; emit success/error inside original branches.
for anchor, kind, failure, success in [
 ('  if (!(printer->driver_data.rstartjob_cb)(job, options, job->printer->device))', 'rstartjob', '    job->state = IPP_JSTATE_ABORTED;\n    goto complete_job;', '  // Print pages...'),
 ('      if (!(filter->cb)(job, job->printer->device, filter->cbdata))', 'filter', '\tjob->state = IPP_JSTATE_ABORTED;', None),
 ('  if (!(job->printer->driver_data.printfile_cb)(job, options, device))', 'printfile', '    papplJobDeletePrintOptions(options);\n    return (false);', '  papplJobDeletePrintOptions(options);\n  papplJobSetImpressionsCompleted(job, 1);')]:
    before('job-process.c', anchor, info('print-dispatch begin callback='+kind))
    if kind == 'filter':
        EXTRA['job-process.c'].append((anchor+'\n'+failure, anchor+'\n      {\n'+info('print-dispatch returned callback=filter result=0')+failure+'\n      }\n      else\n      {\n'+info('print-dispatch returned callback=filter result=1')+'      }'))
    else:
        after('job-process.c', anchor+'\n  {', info('print-dispatch returned callback='+kind+' result=0'))
        before('job-process.c', success, info('print-dispatch returned callback='+kind+' result=1'))
anchor='  options = papplJobCreatePrintOptions(job, 0, job->printer->driver_data.ppm_color > 0);'
before('job-process.c', anchor, info('print-options begin mode=raw'))
after('job-process.c', anchor, info('print-options result=%d mode=raw', ', options != NULL'))
for name, rules in EXTRA.items():
    RULES.setdefault(name, []).extend(rules)

def patch(root):
    header = Path(root) / 'pappl/poc-boundaries.h'
    if header.exists():
        raise ValueError('PAPPL diagnostics header already exists')
    pending = {header: HEADER}
    for name, rules in RULES.items():
        path = Path(root) / 'pappl' / name
        source = path.read_text()
        for old, new in rules:
            if source.count(old) != 1:
                raise ValueError('PAPPL lifecycle anchor mismatch: ' + name)
            source = source.replace(old, new)
        pending[path] = source
    for path, source in pending.items():
        path.write_text(source)

if __name__ == '__main__':
    patch(sys.argv[1])
