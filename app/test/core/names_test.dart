import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/names.dart';

void main() {
  test('a name as a heading starts with a capital and keeps the rest as written', () {
    expect('the inner court'.asHeading, 'The inner court');
    expect('the Azure Cloud Sect'.asHeading, 'The Azure Cloud Sect');
    expect('Zhao Kun'.asHeading, 'Zhao Kun');
    expect('élan vital'.asHeading, 'Élan vital');
    expect('7th Street'.asHeading, '7th Street');
    expect('「蒼雲宗」'.asHeading, '「蒼雲宗」');
    expect('ßtraße'.asHeading, 'ßtraße'); // no one-letter capital: left alone
    expect(''.asHeading, '');
  });
}
