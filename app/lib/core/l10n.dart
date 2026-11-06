import 'package:flutter/widgets.dart';

import '../l10n/gen/app_localizations.dart';

export '../l10n/gen/app_localizations.dart';

/// Every user-facing string comes from `lib/l10n/app_en.arb`, with its Spanish in `app_es.arb`
/// (S10). A test checks that both have the same strings with the same placeholders.
extension L10nContext on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
}
