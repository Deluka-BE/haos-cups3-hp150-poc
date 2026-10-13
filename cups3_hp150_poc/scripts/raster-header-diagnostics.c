/* HP boundary diagnostics: one normal decoder call, no pixel/stream I/O. */
#include <cups/raster.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

_Static_assert(sizeof(unsigned) == 4, "CUPS unsigned ABI changed");
_Static_assert(sizeof(cups_page_header_t) == offsetof(cups_page_header2_t, cupsNumColors),
               "CUPS legacy header must be the exact extended-header prefix");

/* The pinned ULD imports this legacy API. Both CUPS public header APIs use
 * _cupsRasterReadHeader once, then copy (or zero on failure) their header.
 * Use the extended public API to retain cupsNumColors, without a second read.
 * Only this symbol is interposed; pixels, open/close and fd semantics are intact.
 */
unsigned cupsRasterReadHeader(cups_raster_t *r, cups_page_header_t *h)
{
  cups_page_header2_t full;
  unsigned result = cupsRasterReadHeader2(r, &full);
  int saved_errno = errno;
  static int reported;
  memcpy(h, &full, sizeof(*h));
  if (result && !reported)
  {
    char line[256];
    int length;
    reported = 1;
    length = snprintf(line, sizeof(line),
      "HP150_RASTER_HEADER 1 %u %u %u %u %u %u %u %u %u %u %u %u %u %u\n",
      full.cupsWidth, full.cupsHeight, full.HWResolution[0], full.HWResolution[1],
      full.cupsBitsPerColor, full.cupsBitsPerPixel, full.cupsNumColors,
      full.cupsBytesPerLine, (unsigned)full.cupsColorSpace,
      (unsigned)full.cupsColorOrder, full.cupsCompression,
      full.cupsRowCount, full.cupsRowFeed, full.cupsRowStep);
    /* One bounded write; never retry, fail a job, or log library errors. */
    if (length > 0 && (size_t)length < sizeof(line))
      (void)write(STDERR_FILENO, line, (size_t)length);
  }
  errno = saved_errno;
  return result;
}
