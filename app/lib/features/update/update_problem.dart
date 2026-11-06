/// Why an update didn't happen, for the message the banner shows.
enum UpdateProblem implements Exception {
  /// The check or the download failed on the network or the server.
  download,

  /// The file wasn't the one the server described.
  corrupt,

  /// Android wouldn't start installing it, or refused it afterwards.
  install,
}
