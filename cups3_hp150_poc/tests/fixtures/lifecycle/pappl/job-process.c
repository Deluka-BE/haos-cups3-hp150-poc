//
// Job processing (printing) functions for the Printer Application Framework
//
// Copyright © 2019-2022 by Michael R Sweet.
//
// Licensed under Apache License v2.0.  See the file "LICENSE" for more
// information.
//

// Unmodified PAPPL 1.3.1 exact-source anchor excerpts; intervening code omitted.


#include "pappl-private.h"


// Reviewed source excerpt

  // Start processing the job...
  if (start_job(job))
  {

// Reviewed source excerpt
    {
      if (!(filter->cb)(job, job->printer->device, filter->cbdata))
	job->state = IPP_JSTATE_ABORTED;
    }

// Reviewed source excerpt
  // Start processing the job...
  job->streaming = true;

  if (!start_job(job))
    goto complete_job;


// Reviewed source excerpt

  // Open the raster stream...
  if ((ras = cupsRasterOpenIO((cups_raster_cb_t)httpRead, client->http, CUPS_RASTER_READ)) == NULL)
  {
    papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Unable to open raster stream from client - %s", cupsLastErrorString());
    job->state = IPP_JSTATE_ABORTED;

// Reviewed source excerpt

  // Prepare options...
  if (!cupsRasterReadHeader(ras, &header))
  {
    papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Unable to read raster stream from client - %s", cupsLastErrorString());
    job->state = IPP_JSTATE_ABORTED;

// Reviewed source excerpt

  if ((header_pages = header.cupsInteger[CUPS_RASTER_PWG_TotalPageCount]) > 0)
    papplJobSetImpressions(job, (int)header.cupsInteger[CUPS_RASTER_PWG_TotalPageCount]);

  options = papplJobCreatePrintOptions(job, (unsigned)job->impressions, header.cupsBitsPerPixel > 8);

  if (!(printer->driver_data.rstartjob_cb)(job, options, job->printer->device))
  {
    job->state = IPP_JSTATE_ABORTED;

// Reviewed source excerpt

  // Print pages...
  do
  {
    if (job->is_canceled)
      break;

    page ++;

// Reviewed source excerpt

  finish_job(job);
  return;
}

// Reviewed source excerpt
  papplJobSetImpressions(job, 1);
  options = papplJobCreatePrintOptions(job, 0, job->printer->driver_data.ppm_color > 0);

  if (!(job->printer->driver_data.printfile_cb)(job, options, device))
  {
    papplJobDeletePrintOptions(options);

// Reviewed source excerpt

  papplJobDeletePrintOptions(options);
  papplJobSetImpressionsCompleted(job, 1);


// Reviewed source excerpt

  job->state              = IPP_JSTATE_PROCESSING;
  job->processing         = time(NULL);

// Reviewed source excerpt

  // Open the output device...
  if (printer->device_in_use)
  {
    papplLogJob(job, PAPPL_LOGLEVEL_DEBUG, "Waiting for device to become available.");

    while (printer->device_in_use && !printer->is_deleted && !job->is_canceled && papplSystemIsRunning(printer->system))
    {
      _papplRWUnlock(printer);
      sleep(1);
      _papplRWLockWrite(printer);
    }
  }



// Reviewed source excerpt

  while (!printer->device && !printer->is_deleted && !job->is_canceled && papplSystemIsRunning(printer->system))
  {

// Reviewed source excerpt

    printer->device = papplDeviceOpen(printer->device_uri, job->name, papplLogDevice, job->system);


// Reviewed source excerpt

  return (printer->device != NULL);
}
