//
// Job IPP processing for the Printer Application Framework
//
// Copyright © 2019-2022 by Michael R Sweet.
// Copyright © 2010-2019 by Apple Inc.
//
// Licensed under Apache License v2.0.  See the file "LICENSE" for more
// information.
//

// Unmodified source excerpts; intervening source omitted for anchor tests.

  // If we have a PWG or Apple raster file, process it directly or return

// Reviewed source excerpt

    _papplJobProcessRaster(job, client);

// Reviewed source excerpt

  while ((bytes = httpRead(client->http, buffer, sizeof(buffer))) > 0)

// Reviewed source excerpt

    total += (size_t)bytes;

// Reviewed source excerpt

  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "Received %lu bytes of document data.", (unsigned long)total);

// Reviewed source excerpt
      papplClientRespondIPP(client, IPP_STATUS_ERROR_BUSY, "Currently printing another job.");

// Reviewed source excerpt
      papplClientRespondIPP(client, IPP_STATUS_ERROR_NOT_ACCEPTING_JOBS, "Currently holding new jobs.");

// Reviewed source excerpt
  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "Aborting job.");
