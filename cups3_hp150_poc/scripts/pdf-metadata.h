// Bounded PDF metadata only. No shell, raw-output logging, or mutation retry.
#include <poll.h>
#include <signal.h>
#include <sys/wait.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>

#define POC_METADATA_MS 2500
#define POC_METADATA_CAP 16384
static long long pocMetadataNow(void)
{
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
  return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static void pocMetadataMarker(pappl_job_t *job, const char *message)
{
  int saved = errno;
  papplLogJob(job, PAPPL_LOGLEVEL_INFO, "%s", message);
  errno = saved;
}
// Returns only complete, successful output. A full buffer fails open.
static int pocMetadataRun(pappl_job_t *job, const char *tool,
                          const char *filename, char *output)
{
  int fd[2], status = 0, reaped = 0, failed = 0, eof = 0;
  size_t used = 0;
  pid_t pid;
  long long now = pocMetadataNow(), deadline = now + POC_METADATA_MS;
  output[0] = 0;
  pocMetadataMarker(job, "lifecycle stage=retrofit-metadata-launch phase=begin");
  if (now < 0 || !filename || filename[0] != '/' || pipe(fd)) {
    pocMetadataMarker(job, "lifecycle stage=retrofit-metadata-launch phase=end");
    return 0;
  }
  if (fcntl(fd[0], F_SETFL, O_NONBLOCK) < 0 ||
      fcntl(fd[0], F_SETFD, FD_CLOEXEC) < 0 ||
      fcntl(fd[1], F_SETFD, FD_CLOEXEC) < 0) {
    close(fd[0]); close(fd[1]);
    pocMetadataMarker(job, "lifecycle stage=retrofit-metadata-launch phase=end");
    return 0;
  }
  pid = fork();
  if (!pid) {
    int nullfd = open("/dev/null", O_RDWR);
    if (nullfd < 0 || dup2(nullfd, 0) < 0 ||
        dup2(fd[1], 1) < 0 || dup2(nullfd, 2) < 0) _exit(126);
    // Only async-signal-safe operations after fork in the threaded server.
    close(fd[0]); close(fd[1]);
    if (nullfd > 2) close(nullfd);
    char *const argv[] = {(char *)tool, (char *)filename, NULL};
    execv(tool, argv);
    _exit(127);
  }
  close(fd[1]);
  pocMetadataMarker(job, "lifecycle stage=retrofit-metadata-launch phase=end");
  if (pid < 0) { close(fd[0]); return 0; }
  pocMetadataMarker(job, "lifecycle stage=retrofit-metadata-scan phase=begin");
  while (!failed && !(eof && reaped)) {
    now = pocMetadataNow();
    if (now < 0 || now >= deadline) { failed = 1; break; }
    if (!reaped) {
      pid_t r = waitpid(pid, &status, WNOHANG);
      if (r == pid) reaped = 1;
      else if (r < 0 && errno != EINTR) { failed = 1; break; }
    }
    if (!eof) {
      struct pollfd pfd = {fd[0], POLLIN, 0};
      int delay = (int)(deadline - now);
      if (delay > 20) delay = 20;
      int r = poll(&pfd, 1, delay);
      if (r < 0 && errno != EINTR) { failed = 1; break; }
      if (r > 0) {
        ssize_t n = read(fd[0], output + used, POC_METADATA_CAP - used);
        if (n > 0) {
          if (memchr(output + used, 0, (size_t)n)) { failed = 1; break; }
          used += (size_t)n;
          if (used == POC_METADATA_CAP) { failed = 1; break; }
        } else if (!n) eof = 1;
        else if (errno != EINTR && errno != EAGAIN) { failed = 1; break; }
      }
    } else poll(NULL, 0, 20);
  }
  close(fd[0]);
  output[used] = 0;
  pocMetadataMarker(job, "lifecycle stage=retrofit-metadata-scan phase=end");
  pocMetadataMarker(job, "lifecycle stage=retrofit-metadata-wait phase=begin");
  if (!reaped) {
    kill(pid, SIGTERM);
    long long grace = pocMetadataNow() + 100;
    while (!reaped && pocMetadataNow() >= 0 && pocMetadataNow() < grace) {
      pid_t r = waitpid(pid, &status, WNOHANG);
      if (r == pid) reaped = 1;
      else if (r < 0 && errno != EINTR) break;
      if (!reaped) poll(NULL, 0, 5);
    }
    if (!reaped) {
      kill(pid, SIGKILL);
      while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
    }
  }
  pocMetadataMarker(job, "lifecycle stage=retrofit-metadata-wait phase=end");
  pocMetadataMarker(job, failed ? "metadata outcome=bounded-failure" :
                    (WIFEXITED(status) && !WEXITSTATUS(status) ?
                     "metadata outcome=complete" : "metadata outcome=helper-failure"));
  return !failed && WIFEXITED(status) && !WEXITSTATUS(status);
}
