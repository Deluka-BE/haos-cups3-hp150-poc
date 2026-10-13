_prGetFileContentType(pappl_job_t *job)
{
  int        i, j, k;
  const char *informat,
             *filename,
             *found;
  char       command[512],
             line[256];
  char       *p, *q;
  int        creatorline_found = 0;
  pappl_content_t content_type;

  // In the fields "Creator", "Creator Tool", and/or "Producer" of the
  // metadata of a PDF file one usually find the name of the
  // application which created the file. We use thse names to find out
  // the type of content to expect in the file.
  const char *automatic[] =
  { // PAPPL_CONTENT_AUTO
    NULL
  };
  const char *graphics[] =
  { // PAPPL_CONTENT_GRAPHIC
    "Draw",              // LibreOffice
    "Charts",            // LibreOffice
    "Karbon",            // KDE Calligra
    "Flow",              // KDE Calligra
    "Inkscape",
    NULL
  };
  const char *photo[] =
  { // PAPPL_CONTENT_PHOTO
    "imagetopdf",        // CUPS
    "RawTherapee",
    "Darktable",
    "digiKam",
    "Geeqie",
    "GIMP",
    "eog",               // GNOME
    "Skia",              // Google Photos on Android 11 (tested with Pixel 5)
    "ImageMagick",
    "GraphicsMagick",
    "Krita",             // KDE
    "Photoshop",         // Adobe
    "Lightroom",         // Adobe
    "Camera Raw",        // Adobe
    "SilkyPix",
    "Capture One",
    "Photolab",
    "DxO",
    NULL
  };
  const char *text[] =
  { // PAPPL_CONTENT_TEXT
    "texttopdf",         // CUPS
    "GEdit",             // GNOME
    "Writer",            // LibreOffice
    "Word",              // Microsoft Office
    "Words",             // KDE Calligra
    "Kexi",              // KDE Calligra
    "Plan",              // KDE Calligra
    "Braindump",         // KDE Calligra
    "Author",            // KDE Calligra
    "Base",              // LibreOffice
    "Math",              // LibreOffice
    "Pages",             // Mac Office
    "Thunderbird",
    "Bluefish",          // IDEs
    "Geany",             // ...
    "KATE",
    "Eclipse",
    "Brackets",
    "Atom",
    "Sublime",
    "Visual Studio",
    "GNOME Builder",
    "Spacemacs",
    "Atom",
    "CodeLite",          // ...
    "KDevelop",          // IDEs
    "LaTeX",
    "TeX",
    NULL
  };
  const char *text_graphics[] =
  { // PAPPL_CONTENT_TEXT_AND_GRAPHIC
    "evince",            // GNOME
    "Okular",            // KDE
    "Chrome",
    "Chromium",
    "Firefox",
    "Impress",           // LibreOffice
    "Calc",              // LibreOffice
    "Calligra",          // KDE
    "QuarkXPress",
    "InDesign",          // Adobe
    "WPS Presentation",
    "Keynote",           // Mac Office
    "Numbers",           // Mac Office
    "Google",            // Google Docs
    "PowerPoint",        // Microsoft Office
    "Excel",             // Microsoft Office
    "Sheets",            // KDE Calligra
    "Stage",             // KDE Calligra
    NULL
  };

  const char **creating_apps[] =
  {
    automatic,
    graphics,
    photo,
    text,
    text_graphics,
    NULL
  };

  const char * const fields[] =
  {
    "Producer",
    "Creator",
    "Creator Tool",
    NULL
  };


  found = NULL;
  content_type = PAPPL_CONTENT_AUTO;
  informat = papplJobGetDocumentFormat(job, 1);
  if (!strcmp(informat, "image/jpeg"))            // Photos
    content_type = PAPPL_CONTENT_PHOTO;
  else if (!strcmp(informat, "image/png"))        // Screen shots
    content_type = PAPPL_CONTENT_GRAPHIC;
  else if (!strcmp(informat, "application/pdf"))  // PDF, creating app in
                                                  // metadata
  {
    filename = papplJobGetDocumentFilename(job, 1);
    // Run one of the command "pdfinfo" or "exiftool" with the input file,
    // use the first which gets found
    snprintf(command, sizeof(command),
	     "pdfinfo %s 2>/dev/null || exiftool %s 2>/dev/null",
	     filename, filename);
    FILE *pd = popen(command, "r");
    if (!pd)
    {
      papplLogJob(job, PAPPL_LOGLEVEL_WARN,
		  "Unable to get PDF metadata from %s with both pdfinfo and exiftool",
		  filename);
    }
    else
    {
      while (fgets(line, sizeof(line), pd))
      {
	p = line;
	while (isspace(*p))
	  p ++;
	for (i = 0; fields[i]; i ++)
	  if (strncasecmp(p, fields[i], strlen(fields[i])) == 0 &&
	      (isspace(*(p + strlen(fields[i]))) ||
	       *(p + strlen(fields[i])) == ':'))
	    break;
	if (fields[i])
	{
	  p += strlen(fields[i]);
	  while (isspace(*p))
	    p ++;
	  if (*p == ':')
	  {
	    p ++;
	    while (isspace(*p))
	      p ++;
	    while ((q = p + strlen(p) - 1) && (*q == '\n' || *q == '\r'))
	      *q = '\0';
	    papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,
			"PDF metadata line: %s: %s", fields[i], p);
	    creatorline_found = 1;
	    for (j = 0; j < 5; j ++)
	    {
	      for (k = 0; creating_apps[j][k]; k ++)
	      {
		while ((q = strcasestr(p, creating_apps[j][k])))
		  if (!isalnum(*(q - 1)) &&
		      !isalnum(*(q + strlen(creating_apps[j][k]))))
		  {
		    found = creating_apps[j][k];
		    content_type = 1 << j;
		    papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,
				"  Found: %s", creating_apps[j][k]);
		    break;
		  }
		  else
		    p = q;
		if (found)
		  break;
	      }
	      if (found)
		break;
	    }
	  }
	}
	if (found)
	  break;
      }
      pclose(pd);
    }
    if (creatorline_found == 0)
      papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,
		  "No suitable PDF metadata line found");
  }

  papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,
	      "Input file format: %s%s%s%s -> Content optimization: %s",
	      informat,
	      found ? " (" : "", found ? found : "", found ? ")" : "",
	      (content_type == PAPPL_CONTENT_AUTO ? "No optimization" :
	       (content_type == PAPPL_CONTENT_PHOTO ? "Photo" :
		(content_type == PAPPL_CONTENT_GRAPHIC ? "Graphics" :
		 (content_type == PAPPL_CONTENT_TEXT ? "Text" :
		  "Text and graphics")))));

  return (content_type);
}
