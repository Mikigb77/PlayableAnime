import 'package:flutter/widgets.dart';
import 'package:intl/intl.dart';

/// Credits are US cents, often fractional (a turn costs about 2 cents, K2). Amounts under a
/// dollar read as cents ("48¢", "2.3¢"), larger ones as dollars ("$1.50").
String formatCredits(BuildContext context, num cents, {bool signed = false}) =>
    formatCreditsIn(Localizations.localeOf(context).toLanguageTag(), cents, signed: signed);

String formatCreditsIn(String locale, num cents, {bool signed = false}) {
  final abs = cents.abs();
  final String text;
  if (abs >= 100) {
    text = NumberFormat.simpleCurrency(locale: locale, name: 'USD').format(abs / 100);
  } else {
    // Tenths of a cent at most, and none on a whole number.
    final rounded = (abs * 10).round() / 10;
    text = '${NumberFormat('#,##0.#', locale).format(rounded)}¢';
  }
  if (!signed || cents == 0) return text;
  // U+2212, the minus sign, which lines up with the plus.
  return '${cents > 0 ? '+' : '−'}$text';
}
