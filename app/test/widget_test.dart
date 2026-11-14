
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:airway/features/welcome/presentation/welcome_screen.dart';

void main() {
  testWidgets('AIRway welcome screen loads', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: WelcomeScreen(),
      ),
    );

    expect(find.text('AIRway'), findsOneWidget);
    expect(
      find.text('Home services, made simple.'),
      findsOneWidget,
    );
    expect(find.text('Get Started'), findsOneWidget);
    expect(
      find.byIcon(Icons.home_repair_service_rounded),
      findsOneWidget,
    );
  });
}
