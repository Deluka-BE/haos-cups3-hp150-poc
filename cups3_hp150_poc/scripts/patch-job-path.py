#!/usr/bin/python3
"""Fail closed against pinned retrofit source; fixed-label job path diagnostics."""
from pathlib import Path
import sys


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Pinned job-path patch anchor mismatch')
    return source.replace(old, new)


def patch(root):
    path = Path(root) / 'pappl-retrofit/print-job.c'
    s = path.read_text()
    helper = '''
// PoC: only allow known MIME labels into diagnostics, never client strings.
static const char *pocFormat(pappl_job_t *job)
{
  const char *f = papplJobGetDocumentFormat(job, 1);
  if (!f) return "unknown";
  if (!strcmp(f, "image/urf")) return "urf";
  if (!strcmp(f, "image/pwg-raster")) return "pwg-raster";
  if (!strcmp(f, "application/pdf")) return "pdf";
  if (!strcmp(f, "image/jpeg")) return "jpeg";
  if (!strcmp(f, "image/png")) return "png";
  return "other";
}

'''
    helper += r"""
static const char *pocBinding(const char *uri)
{
  if (!uri || !*uri) return "invalid";
  for (const unsigned char *p = (const unsigned char *)uri; *p; p++)
    if (*p <= 32 || *p == 127) return "invalid";
  if (!strncmp(uri, "cups:usb://", 11) && uri[11]) return "cups:usb";
  if (!strncmp(uri, "usb://", 6) && uri[6]) return "usb";
  if (!strncmp(uri, "usb:", 4) || !strncmp(uri, "cups:usb:", 9)) return "invalid";
  if (!strcmp(uri, "capture:/hp150") || !strcmp(uri, "cups:capture:/hp150")) return "capture";
  return strchr(uri, ':') ? "other" : "invalid";
}
static void pocLogBinding(pappl_job_t *job)
{
  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path binding=%s",
    pocBinding(papplPrinterGetDeviceURI(papplJobGetPrinter(job))));
}
"""
    helper += r"""
typedef struct { cf_filter_filter_in_chain_t original; int index; } poc_stage_t;
static int pocStage(int in, int out, int seekable, cf_filter_data_t *data, void *params)
{
  poc_stage_t *p = params;
  if (data->logfunc) data->logfunc(data->logdata, CF_LOGLEVEL_INFO,
    "path stage=filter-%d started", p->index);
  int result = p->original.function(in, out, seekable, data, p->original.parameters);
  if (data->logfunc) data->logfunc(data->logdata, CF_LOGLEVEL_INFO,
    "path stage=filter-%d finished exit=%d", p->index, result);
  return result;
}
static int pocChain(int in, int out, int seekable, cf_filter_data_t *data, void *params)
{
  cups_array_t *original = params;
  int count = cupsArrayGetCount(original);
  poc_stage_t *stages = calloc(count, sizeof(*stages));
  cf_filter_filter_in_chain_t *filters = calloc(count, sizeof(*filters));
  cups_array_t *chain = cupsArrayNew(NULL, NULL, NULL, 0, NULL, NULL);
  if (!stages || !filters || !chain) { free(stages); free(filters); if (chain) cupsArrayDelete(chain); return 1; }
  for (int i = 0; i < count; i++) {
    stages[i].original = *(cf_filter_filter_in_chain_t *)cupsArrayGetElement(original, i);
    stages[i].index = i;
    filters[i] = stages[i].original;
    filters[i].function = pocStage;
    filters[i].parameters = &stages[i];
    cupsArrayAdd(chain, &filters[i]);
  }
  int result = cfFilterChain(in, out, seekable, data, chain);
  cupsArrayDelete(chain); free(filters); free(stages);
  return result;
}
"""
    s = replace(s, '//\n// \'_prASCII85()\'', helper + '//\n// \'_prASCII85()\'')
    s = replace(s, '  informat = papplJobGetDocumentFormat(job, 1);\n  papplLogJob',
                '  pocLogBinding(job);\n  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path accepted format=%s source=spooled", pocFormat(job));\n  informat = papplJobGetDocumentFormat(job, 1);\n  papplLogJob')
    s = replace(s, '  // Load PPD file and determine the PPD options equivalent to the job options\n  job_data = _prCreateJobData(job, options);\n  papplLogJob',
                '  pocLogBinding(job);\n  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path accepted format=%s source=streaming", pocFormat(job));\n  // Load PPD file and determine the PPD options equivalent to the job options\n  job_data = _prCreateJobData(job, options);\n  papplLogJob')
    s = replace(s, '  if (cfFilterChain(fd, nullfd, 1, job_data->filter_data, job_data->chain) == 0)\n    ret = true;',
                '''  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path stage=filter-chain started source=spooled");
  int poc_result = cfFilterChain(fd, nullfd, 1, job_data->filter_data, job_data->chain);
  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path stage=filter-chain finished exit=%d", poc_result);
  if (poc_result == 0) ret = true;''')
    s = replace(s, '  job_data->device_fd = cfFilterPOpen(cfFilterChain',
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path stage=filter-chain started source=streaming");\n  job_data->device_fd = cfFilterPOpen(cfFilterChain')
    s = replace(s, '  cfFilterPClose(job_data->device_fd, job_data->device_pid,\n\t       job_data->filter_data);',
                '''  int poc_result = cfFilterPClose(job_data->device_fd, job_data->device_pid,
                               job_data->filter_data);
  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path stage=filter-chain finished exit=%d", poc_result);''')
    # Final sink: bounded summary, no document bytes or filenames.
    s = replace(s, '  int                  debug_fd = -1;         // File descriptor for debug copy',
                '  unsigned long long poc_bytes = 0;\n  int                  debug_fd = -1;         // File descriptor for debug copy')
    s = replace(s, '  while ((bytes = read(inputfd, buffer, sizeof(buffer))) > 0)\n  {\n    if (debug_fd >= 0)',
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path stage=backend-handoff started");\n  while ((bytes = read(inputfd, buffer, sizeof(buffer))) > 0)\n  {\n    if (debug_fd >= 0)')
    s = replace(s, '      close(inputfd);\n      close(outputfd);\n      return (1);\n    }\n  }\n  papplDeviceFlush(device);',
                '''      papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "path stage=backend-handoff failed errno=%d bytes=%llu", errno, poc_bytes);
      close(inputfd);
      close(outputfd);
      return (1);
    }
    if (!poc_bytes)
      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path stage=backend-handoff first-write bytes=%d", (int)bytes);
    poc_bytes += (unsigned long long)bytes;
  }
  papplLogJob(job, bytes < 0 ? PAPPL_LOGLEVEL_ERROR : PAPPL_LOGLEVEL_INFO,
              "path stage=backend-handoff finished bytes=%llu read-errno=%d", poc_bytes, bytes < 0 ? errno : 0);
  papplDeviceFlush(device);''')
    s = replace(s, '  bool                  ret = true;          // Return value',
                '  unsigned long long poc_bytes = 0;\n  bool                  ret = true;          // Return value')
    s = replace(s, '  papplJobSetImpressions(job, 1);\n\n  if ((fd = open(papplJobGetDocumentFilename(job, 1), O_RDONLY)) < 0)',
                '  pocLogBinding(job);\n  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path accepted format=%s source=raw filter-chain=bypassed", pocFormat(job));\n  papplJobSetImpressions(job, 1);\n\n  if ((fd = open(papplJobGetDocumentFilename(job, 1), O_RDONLY)) < 0)')
    s = replace(s, '      close(fd);\n      ret = false;\n      goto cleanup;\n    }\n  }\n  close(fd);',
                '''      papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "path stage=backend-handoff failed errno=%d bytes=%llu", errno, poc_bytes);
      close(fd);
      ret = false;
      goto cleanup;
    }
    if (!poc_bytes)
      papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path stage=backend-handoff first-write bytes=%d", (int)bytes);
    poc_bytes += (unsigned long long)bytes;
  }
  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "path stage=backend-handoff finished bytes=%llu read-errno=%d", poc_bytes, bytes < 0 ? errno : 0);
  close(fd);''')
    s = s.replace("= cfFilterChain(fd,", "= pocChain(fd,").replace("cfFilterPOpen(cfFilterChain,", "cfFilterPOpen(pocChain,")
    # Earliest safe retrofit callback entries, before 0.1.17 binding logs.
    s = replace(s, '  job_options = papplJobCreatePrintOptions(job, 1, INT_MAX, 1);',
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=retrofit-entry mode=spooled");\n  job_options = papplJobCreatePrintOptions(job, 1, INT_MAX, 1);')
    s = replace(s, '  papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,\n\t      "Printing job in streaming mode");',
                '  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=retrofit-entry mode=streaming");\n  papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,\n\t      "Printing job in streaming mode");')
    s = replace(s, '  if (!job || !device)\n    return (false);',
                '  if (!job || !device)\n    return (false);\n  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=retrofit-entry mode=raw");')
    path.write_text(s)
    path = Path(root) / 'pappl-retrofit/cups-backends.c'
    s = path.read_text()
    s = replace(s, '    cfFilterPClose(device_data->inputfd, device_data->backend_pid,\n\t\t device_data->filter_data);',
                '''    int poc_result = cfFilterPClose(device_data->inputfd, device_data->backend_pid,
                                  device_data->filter_data);
    if (device_data->filter_data && device_data->filter_data->logfunc)
      device_data->filter_data->logfunc(device_data->filter_data->logdata,
        CF_LOGLEVEL_INFO, "path stage=cups-backend finished exit=%d", poc_result);''')
    path.write_text(s)


if __name__ == '__main__':
    patch(sys.argv[1])
