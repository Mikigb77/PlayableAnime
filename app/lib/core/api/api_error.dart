import 'dart:convert';

/// Error codes from docs/API.md (T7), plus the ones the client produces itself.
enum ApiErrorCode {
  validationError('validation_error'),
  birthDateRequired('birth_date_required'),
  unauthenticated('unauthenticated'),
  outOfCredits('out_of_credits'),
  forbidden('forbidden'),
  notFound('not_found'),
  versionConflict('version_conflict'),
  unreadableAction('unreadable_action'),
  badKey('bad_key'),
  rateLimited('rate_limited'),
  quotaExceeded('quota_exceeded'),
  llmUnavailable('llm_unavailable'),

  // Client side: no envelope came back.

  /// No connection, or it dropped before a reply (including a stream that ended early).
  network('network'),

  /// The server took too long to answer.
  timeout('timeout'),

  /// A 5xx or other reply without the error envelope.
  server('server'),

  /// An envelope with a code this build doesn't know.
  unknown('unknown');

  const ApiErrorCode(this.wire);

  /// The code as it appears in the API's JSON.
  final String wire;

  static ApiErrorCode fromWire(String? code) {
    for (final value in values) {
      if (value.wire == code) return value;
    }
    return unknown;
  }

  /// Whether simply trying again may work.
  bool get isRetryable => switch (this) {
    network || timeout || server || llmUnavailable || rateLimited || versionConflict => true,
    _ => false,
  };
}

/// A typed API failure. Every error the app shows comes through this type.
class ApiException implements Exception {
  const ApiException(this.code, {this.message = '', this.status, this.details = const {}});

  /// Parses an error envelope `{"error": {"code", "message", "details"}}`. Bodies without one
  /// (a proxy's HTML page, an empty 502) become [ApiErrorCode.server] or a status-based code.
  factory ApiException.fromResponse(int status, String body) {
    Object? decoded;
    try {
      decoded = body.isEmpty ? null : jsonDecode(body);
    } on FormatException {
      decoded = null;
    }
    if (decoded case {'error': final Map<String, dynamic> error}) {
      return ApiException(
        ApiErrorCode.fromWire(error['code'] as String?),
        message: error['message'] as String? ?? '',
        status: status,
        details: error['details'] as Map<String, dynamic>? ?? const {},
      );
    }
    final code = switch (status) {
      401 => ApiErrorCode.unauthenticated,
      403 => ApiErrorCode.forbidden,
      404 => ApiErrorCode.notFound,
      409 => ApiErrorCode.versionConflict,
      429 => ApiErrorCode.rateLimited,
      _ => ApiErrorCode.server,
    };
    return ApiException(code, status: status);
  }

  final ApiErrorCode code;

  /// The server's human-readable text. The app shows its own localized copy instead
  /// (see `describeApiError`), so this is for logs and debugging.
  final String message;
  final int? status;
  final Map<String, dynamic> details;

  /// `out_of_credits`: the balance in cents (may be fractional).
  num? get balanceCents => details['balance_cents'] as num?;

  /// `version_conflict`: the story's current version (T10).
  int? get currentVersion => (details['current_version'] as num?)?.toInt();

  /// `rate_limited`: how long to wait.
  Duration? get retryAfter => switch (details['retry_after_s']) {
    final num s => Duration(milliseconds: (s * 1000).round()),
    _ => null,
  };

  /// `quota_exceeded`: when the daily quota resets.
  DateTime? get resetsAt => switch (details['resets_at']) {
    final String s => DateTime.tryParse(s),
    _ => null,
  };

  /// `validation_error`: the problems per field, as the server lists them.
  List<Object?> get fields => details['fields'] as List<Object?>? ?? const [];

  @override
  String toString() => 'ApiException(${code.wire}, status: $status, message: $message)';
}
