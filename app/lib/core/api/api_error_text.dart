import '../l10n.dart';
import 'api_error.dart';

/// What the app tells the player about an error: a short title and one helpful sentence. The
/// server's own message is never shown, because it isn't localized.
typedef ErrorCopy = ({String title, String message});

ErrorCopy describeError(AppLocalizations l10n, Object error) {
  final code = error is ApiException ? error.code : ApiErrorCode.unknown;
  return switch (code) {
    ApiErrorCode.network => (title: l10n.errorNetworkTitle, message: l10n.errorNetwork),
    ApiErrorCode.timeout => (title: l10n.errorTimeoutTitle, message: l10n.errorTimeout),
    ApiErrorCode.server ||
    ApiErrorCode.internalError => (title: l10n.errorGenericTitle, message: l10n.errorServer),
    ApiErrorCode.unauthenticated => (
      title: l10n.errorUnauthenticatedTitle,
      message: l10n.errorUnauthenticated,
    ),
    ApiErrorCode.outOfCredits => (
      title: l10n.errorOutOfCreditsTitle,
      message: l10n.errorOutOfCredits,
    ),
    ApiErrorCode.forbidden => (title: l10n.errorForbiddenTitle, message: l10n.errorForbidden),
    ApiErrorCode.notFound => (title: l10n.errorNotFoundTitle, message: l10n.errorNotFound),
    ApiErrorCode.versionConflict => (
      title: l10n.errorVersionConflictTitle,
      message: l10n.errorVersionConflict,
    ),
    ApiErrorCode.unreadableAction => (
      title: l10n.errorUnreadableActionTitle,
      message: l10n.errorUnreadableAction,
    ),
    ApiErrorCode.badKey => (title: l10n.errorBadKeyTitle, message: l10n.errorBadKey),
    ApiErrorCode.rateLimited => (
      title: l10n.errorRateLimitedTitle,
      message: switch ((error as ApiException).retryAfter) {
        final wait? => l10n.errorRateLimitedWait(wait.inSeconds.clamp(1, 3600)),
        null => l10n.errorRateLimited,
      },
    ),
    ApiErrorCode.quotaExceeded => (title: l10n.errorQuotaTitle, message: l10n.errorQuota),
    ApiErrorCode.llmUnavailable => (title: l10n.errorLlmTitle, message: l10n.errorLlm),
    ApiErrorCode.validationError => (
      title: l10n.errorValidationTitle,
      message: l10n.errorValidation,
    ),
    ApiErrorCode.birthDateRequired => (
      title: l10n.errorBirthDateTitle,
      message: l10n.errorBirthDate,
    ),
    ApiErrorCode.signInUnavailable => (
      title: l10n.errorSignInUnavailableTitle,
      message: l10n.errorSignInUnavailable,
    ),
    ApiErrorCode.methodNotAllowed ||
    ApiErrorCode.unknown => (title: l10n.errorGenericTitle, message: l10n.errorUnknown),
  };
}
