import 'package:firebase_auth/firebase_auth.dart';
import 'package:google_sign_in/google_sign_in.dart';

class GoogleSignInService {
  GoogleSignInService._();

  static final GoogleSignIn _googleSignIn = GoogleSignIn(
    scopes: ['email', 'profile'],
  );

  static Future<String?> signIn() async {
    try {
      final GoogleSignInAccount? account = await _googleSignIn.signIn();
      if (account == null) return null;

      final GoogleSignInAuthentication googleAuth =
          await account.authentication;
      final credential = GoogleAuthProvider.credential(
        idToken: googleAuth.idToken,
        accessToken: googleAuth.accessToken,
      );

      final userCredential =
          await FirebaseAuth.instance.signInWithCredential(credential);
      final firebaseUser = userCredential.user;
      if (firebaseUser == null) return null;

      return await firebaseUser.getIdToken();
    } on Exception {
      rethrow;
    }
  }

  static Future<void> signOut() async {
    await _googleSignIn.signOut();
    await FirebaseAuth.instance.signOut();
  }
}