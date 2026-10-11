//
// PPD/Classic CUPS driver retro-fit Printer Application Library
// (libpappl-retrofit) for the Printer Application Framework (PAPPL)
//
// print-job.c
//
// Copyright © 2020 by Till Kamppeter.
// Copyright © 2020 by Michael R Sweet.
//
// Licensed under Apache License v2.0.  See the file "LICENSE" for more
// information.
//

// Unmodified source excerpts; intervening source omitted for anchor tests.
//
// '_prASCII85()' - Print binary data as a series of base-85 numbers.

// Reviewed source excerpt
  job_options = papplJobCreatePrintOptions(job, 1, INT_MAX, 1);

// Reviewed source excerpt
  informat = papplJobGetDocumentFormat(job, 1);
  papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,

// Reviewed source excerpt
  if (cfFilterChain(fd, nullfd, 1, job_data->filter_data, job_data->chain) == 0)
    ret = true;

// Reviewed source excerpt
  int                  debug_fd = -1;         // File descriptor for debug copy

// Reviewed source excerpt
  while ((bytes = read(inputfd, buffer, sizeof(buffer))) > 0)
  {
    if (debug_fd >= 0)

// Reviewed source excerpt
      close(inputfd);
      close(outputfd);
      return (1);
    }
  }
  papplDeviceFlush(device);

// Reviewed source excerpt
  bool                  ret = true;          // Return value

// Reviewed source excerpt
  if (!job || !device)
    return (false);

// Reviewed source excerpt
  papplJobSetImpressions(job, 1);

  if ((fd = open(papplJobGetDocumentFilename(job, 1), O_RDONLY)) < 0)

// Reviewed source excerpt
      close(fd);
      ret = false;
      goto cleanup;
    }
  }
  close(fd);

// Reviewed source excerpt
  papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,
	      "Printing job in streaming mode");

// Reviewed source excerpt
  // Load PPD file and determine the PPD options equivalent to the job options
  job_data = _prCreateJobData(job, options);
  papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,

// Reviewed source excerpt
  job_data->device_fd = cfFilterPOpen(cfFilterChain, -1, nullfd,

// Reviewed source excerpt
  cfFilterPClose(job_data->device_fd, job_data->device_pid,
	       job_data->filter_data);
