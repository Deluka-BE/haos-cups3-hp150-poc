/* Synthetic CUPS raster only; never opens a device or uses vendor code. */
#include <cups/raster.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv)
{
  if (argc < 2) return 2;
  if (!strcmp(argv[1], "write"))
  {
    int mode = atoi(argv[2]), layout = atoi(argv[3]);
    cups_raster_t *r = cupsRasterOpen(1, (cups_mode_t)mode);
    cups_page_header2_t h;
    unsigned char row[64];
    memset(&h, 0, sizeof(h));
    strcpy(h.MediaClass, "HEADER_SECRET");
    strcpy(h.cupsPageSizeName, "SIZE_SECRET");
    h.HWResolution[0] = 600; h.HWResolution[1] = 600;
    h.PageSize[0] = 612; h.PageSize[1] = 792;
    h.cupsWidth = 13; h.cupsHeight = 3;
    h.cupsBitsPerColor = layout == 3 ? 1 : 8;
    h.cupsNumColors = layout == 3 ? 1 : 3;
    h.cupsBitsPerPixel = layout == 0 ? 24 : h.cupsBitsPerColor;
    h.cupsColorSpace = layout == 3 ? CUPS_CSPACE_K : CUPS_CSPACE_RGB;
    h.cupsColorOrder = layout == 1 ? CUPS_ORDER_BANDED :
                        layout == 2 ? CUPS_ORDER_PLANAR : CUPS_ORDER_CHUNKED;
    h.cupsBytesPerLine = layout == 0 || layout == 1 ? 39 : layout == 2 ? 13 : 2;
    h.cupsRowCount = 0; h.cupsRowFeed = 0; h.cupsRowStep = 0;
    for (unsigned i = 0; i < sizeof(row); i++) row[i] = (unsigned char)(i * 17 + 5);
    for (int page = 0; page < 2; page++)
    {
      unsigned rows = h.cupsHeight * (layout == 2 ? h.cupsNumColors : 1);
      if (!cupsRasterWriteHeader2(r, &h)) return 3;
      for (unsigned y = 0; y < rows; y++)
        if (cupsRasterWritePixels(r, row, h.cupsBytesPerLine) != h.cupsBytesPerLine) return 4;
    }
    cupsRasterClose(r);
    return 0;
  }
  if (!strcmp(argv[1], "read"))
  {
    int fd = argc > 2 ? open(argv[2], O_RDONLY) : 0;
    cups_raster_t *r = cupsRasterOpen(fd, CUPS_RASTER_READ);
    cups_page_header_t h;
    unsigned char row[256];
    if (!r) { printf("open-failure\n"); return 0; }
    for (int page = 0; page < 4; page++)
    {
      errno = EACCES;
      memset(&h, 0xa5, sizeof(h));
      unsigned result = cupsRasterReadHeader(r, &h);
      int saved = errno;
      printf("header %u errno %d\n", result, saved);
      fwrite(&h, 1, sizeof(h), stdout);
      if (!result) break;
      unsigned colors = h.cupsColorSpace == CUPS_CSPACE_K ? 1 : 3;
      unsigned rows = h.cupsHeight * (h.cupsColorOrder == CUPS_ORDER_PLANAR ? colors : 1);
      if (h.cupsBytesPerLine > sizeof(row) || rows > 32) return 5;
      for (unsigned y = 0; y < rows; y++)
      {
        unsigned n = cupsRasterReadPixels(r, row, h.cupsBytesPerLine);
        printf("pixels %u\n", n);
        fwrite(row, 1, n, stdout);
      }
    }
    cupsRasterClose(r);
    if (fd != 0) close(fd);
    return 0;
  }
  return 2;
}
