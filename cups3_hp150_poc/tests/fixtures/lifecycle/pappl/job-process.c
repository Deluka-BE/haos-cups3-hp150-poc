//
// Job processing (printing) functions for the Printer Application Framework
//
// Copyright © 2019-2022 by Michael R Sweet.
//
// Licensed under Apache License v2.0.  See the file "LICENSE" for more
// information.
//

// Unmodified source excerpts; intervening source omitted for anchor tests.

  // Start processing the job...
  if (start_job(job))

// Reviewed source excerpt
  // Start processing the job...
  job->streaming = true;

// Reviewed source excerpt
  {
    papplLogJob(job, PAPPL_LOGLEVEL_DEBUG, "Waiting for device to become available.");

// Reviewed source excerpt

    printer->device = papplDeviceOpen(printer->device_uri, job->name, papplLogDevice, job->system);

// Reviewed source excerpt

  return (printer->device != NULL);

// Reviewed source excerpt
  finish_job(job);
  return;
