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

def patch(root):
    pending = {}
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
