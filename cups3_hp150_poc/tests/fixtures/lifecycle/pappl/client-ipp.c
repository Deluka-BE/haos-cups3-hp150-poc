//
// Common client IPP processing for the Printer Application Framework
//
// Copyright © 2019-2020 by Michael R Sweet.
// Copyright © 2010-2019 by Apple Inc.
//
// Licensed under Apache License v2.0.  See the file "LICENSE" for more
// information.
//

// Unmodified source excerpts; intervening source omitted for anchor tests.
  major = ippGetVersion(client->request, &minor);
  op    = ippGetOperation(client->request);
