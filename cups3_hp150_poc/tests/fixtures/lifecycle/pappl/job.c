//
// Job object for the Printer Application Framework
//
// Copyright © 2019-2022 by Michael R Sweet.
// Copyright © 2010-2019 by Apple Inc.
//
// Licensed under Apache License v2.0.  See the file "LICENSE" for more
// information.
//

// Unmodified source excerpts; intervening source omitted for anchor tests.

  if (printer->max_active_jobs > 0 && (int)cupsArrayGetCount(printer->active_jobs) >= printer->max_active_jobs)
  {

// Reviewed source excerpt
  {
    papplLog(printer->system, PAPPL_LOGLEVEL_ERROR, "Unable to allocate memory for job: %s", strerror(errno));

// Reviewed source excerpt

  cupsArrayAdd(printer->all_jobs, job);

// Reviewed source excerpt
      // Process the job...
      job->state = IPP_JSTATE_PENDING;
      _papplPrinterCheckJobs(job->printer);
    }
  }
  else

// Reviewed source excerpt

      papplLogPrinter(printer, PAPPL_LOGLEVEL_DEBUG, "Starting job %d.", job->job_id);

// Reviewed source excerpt
      {
	job->state     = IPP_JSTATE_ABORTED;
	job->completed = time(NULL);

// Reviewed source excerpt
      }
      else
	pthread_detach(t);
