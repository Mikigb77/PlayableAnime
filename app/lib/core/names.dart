/// Names from the world, shown as headings.
extension NameAsHeading on String {
  /// The name with a capital first letter and the rest as the world wrote it. The world writes a
  /// name the way a sentence holds it ("the inner court"); as a heading or a card's title it starts
  /// with a capital ("The inner court"). Anything already capitalized, or with no letter first,
  /// stays as it is.
  String get asHeading {
    if (isEmpty) return this;
    final first = String.fromCharCode(runes.first);
    final capital = first.toUpperCase();
    if (capital == first || capital.length != first.length) return this;
    return '$capital${substring(first.length)}';
  }
}
