import 'package:flutter/widgets.dart';
import 'package:google_sign_in_web/web_only.dart' as web;

/// On the web only Google's own button can sign in (Google Identity Services). Its sign-ins
/// arrive on `GoogleAuth.idTokens`.
Widget googleWebButton({required bool dark, required double width}) => web.renderButton(
  configuration: web.GSIButtonConfiguration(
    theme: dark ? web.GSIButtonTheme.filledBlack : web.GSIButtonTheme.outline,
    size: web.GSIButtonSize.large,
    text: web.GSIButtonText.continueWith,
    shape: web.GSIButtonShape.pill,
    logoAlignment: web.GSIButtonLogoAlignment.center,
    minimumWidth: width.clamp(200, 400),
  ),
);
