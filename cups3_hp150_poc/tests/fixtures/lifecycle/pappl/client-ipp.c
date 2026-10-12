//
// Common client IPP processing for the Printer Application Framework
//
// Copyright © 2019-2020 by Michael R Sweet.
// Copyright © 2010-2019 by Apple Inc.
//
// Licensed under Apache License v2.0.  See the file "LICENSE" for more
// information.
//

// Unmodified PAPPL 1.3.1 exact-source anchor excerpts; intervening code omitted.


#include "pappl-private.h"


// Reviewed source excerpt
{
  char temp;				// Data


  if (httpGetState(client->http) != HTTP_STATE_POST_RECV)
    return (false);
  else
    return (httpPeek(client->http, &temp, 1) > 0);
}

// Reviewed source excerpt
  major = ippGetVersion(client->request, &minor);
  op    = ippGetOperation(client->request);


// Reviewed source excerpt

  // Send the HTTP header and return...
  if (httpGetState(client->http) != HTTP_STATE_POST_SEND)
