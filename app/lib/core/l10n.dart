import 'package:flutter/widgets.dart';

import '../l10n/gen/app_localizations.dart';

export '../l10n/gen/app_localizations.dart';

/// Every user-facing string comes from `lib/l10n/app_en.arb` (S10). Spanish is added as
/// `app_es.arb` when it ships.
extension L10nContext on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
}
