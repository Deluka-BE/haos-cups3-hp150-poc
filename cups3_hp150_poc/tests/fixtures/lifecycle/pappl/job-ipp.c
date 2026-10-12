//
// Job IPP processing for the Printer Application Framework
//
// Copyright © 2019-2022 by Michael R Sweet.
// Copyright © 2010-2019 by Apple Inc.
//
// Licensed under Apache License v2.0.  See the file "LICENSE" for more
// information.
//

// Unmodified PAPPL 1.3.1 exact-source anchor excerpts; intervening code omitted.


#include "pappl-private.h"


// Reviewed source excerpt

  // If we have a PWG or Apple raster file, process it directly or return
  // server-error-busy...

// Reviewed source excerpt
    {
      papplClientRespondIPP(client, IPP_STATUS_ERROR_BUSY, "Currently printing another job.");
      _papplRWUnlock(job->printer);

// Reviewed source excerpt
    {
      papplClientRespondIPP(client, IPP_STATUS_ERROR_NOT_ACCEPTING_JOBS, "Currently holding new jobs.");
      _papplRWUnlock(job->printer);

// Reviewed source excerpt

    _papplJobProcessRaster(job, client);


// Reviewed source excerpt

  // Create a file for the request data...
  if ((job->fd = papplJobOpenFile(job, filename, sizeof(filename), client->system->directory, NULL, "w")) < 0)

// Reviewed source excerpt

  while ((bytes = httpRead(client->http, buffer, sizeof(buffer))) > 0)
  {

// Reviewed source excerpt

    total += (size_t)bytes;
  }

  if (bytes < 0)
  {

// Reviewed source excerpt

  if (close(job->fd))
  {

// Reviewed source excerpt

    papplClientRespondIPP(client, IPP_STATUS_ERROR_INTERNAL, "Unable to write print file: %s", strerror(error));

    goto abort_job;
  }

  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "Received %lu bytes of document data.", (unsigned long)total);


// Reviewed source excerpt
  // Submit the job for processing...
  _papplJobSubmitFile(job, filename);


// Reviewed source excerpt

  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "Aborting job.");
