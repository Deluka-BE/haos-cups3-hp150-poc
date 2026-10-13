#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
int main(int argc, char **argv)
{
  const char *mode = getenv(strstr(argv[0], "pdfinfo") ? "PDF_MODE" : "EXIF_MODE");
  const char *expected = getenv("EXPECTED_FILENAME");
  if (argc != 2 || !expected || strcmp(argv[1], expected)) return 9;
  fputs("STDERR_SECRET", stderr);
  if (!mode || !strcmp(mode, "fail")) return 1;
  if (!strcmp(mode, "empty")) return 0;
  if (!strcmp(mode, "hang")) { for (;;) pause(); }
  if (!strcmp(mode, "ignore-term")) { signal(SIGTERM, SIG_IGN); for (;;) pause(); }
  if (!strcmp(mode, "close-hang")) { close(1); for (;;) pause(); }
  if (!strcmp(mode, "large")) { for (int i=0;i<100000;i++) putchar('X'); return 0; }
  if (!strcmp(mode, "nul")) { fwrite("Creator: Word\0SECRET", 1, 20, stdout); return 0; }
  if (!strcmp(mode, "no-newline")) { fputs("Creator: Word", stdout); return 0; }
  if (!strcmp(mode, "empty-value")) { puts("Creator:"); return 0; }
  if (!strcmp(mode, "malformed")) { puts("Creator Word\nProducer: SwordWordWord"); return 0; }
  if (!strcmp(mode, "unknown")) { puts("Creator: METADATA_SECRET"); return 0; }
  if (!strcmp(mode, "photo")) { puts("Producer: Skia"); return 0; }
  if (!strcmp(mode, "graphics")) { puts("Creator: Inkscape"); return 0; }
  if (!strcmp(mode, "combined")) { puts("Creator Tool: Chrome"); return 0; }
  if (!strcmp(mode, "nonzero-output")) { puts("Creator: Word"); return 1; }
  puts("Producer: METADATA_SECRET\nCreator: Microsoft Word");
  return 0;
}
