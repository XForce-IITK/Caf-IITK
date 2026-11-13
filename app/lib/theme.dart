import 'package:flutter/material.dart';

/// Caf@IITK's look (CAFIITK-208): a quiet, neutral palette with one warm
/// accent, white surfaces separated by hairline borders rather than shadows,
/// and the Inter typeface. Purely visual: no screen depends on these values.
abstract final class CafColors {
  static const background = Color(0xFFF7F6F3);
  static const surface = Color(0xFFFFFFFF);
  static const subtle = Color(0xFFF1EFEB);
  static const border = Color(0xFFE5E2DC);
  static const ink = Color(0xFF1C1B19);
  static const muted = Color(0xFF6E6A63);
  static const faint = Color(0xFFA19C94);

  /// The brand accent, used sparingly: the logo mark.
  static const accent = Color(0xFFC2410C);
  static const error = Color(0xFFB42318);
}

const _font = 'Inter';
const _radius = 10.0;

ThemeData buildCafTheme() {
  final scheme =
      ColorScheme.fromSeed(
        seedColor: CafColors.accent,
        brightness: Brightness.light,
      ).copyWith(
        primary: CafColors.ink,
        onPrimary: Colors.white,
        primaryContainer: CafColors.subtle,
        onPrimaryContainer: CafColors.ink,
        secondary: CafColors.muted,
        onSecondary: Colors.white,
        secondaryContainer: CafColors.subtle,
        onSecondaryContainer: CafColors.ink,
        tertiary: CafColors.accent,
        onTertiary: Colors.white,
        error: CafColors.error,
        onError: Colors.white,
        surface: CafColors.surface,
        onSurface: CafColors.ink,
        onSurfaceVariant: CafColors.muted,
        surfaceTint: Colors.transparent,
        surfaceContainerLowest: CafColors.surface,
        surfaceContainerLow: CafColors.surface,
        surfaceContainer: CafColors.surface,
        surfaceContainerHigh: CafColors.surface,
        surfaceContainerHighest: CafColors.subtle,
        outline: CafColors.border,
        outlineVariant: CafColors.border,
      );

  final base = ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    fontFamily: _font,
  );
  final text = base.textTheme
      .copyWith(
        headlineMedium: base.textTheme.headlineMedium?.copyWith(
          fontWeight: FontWeight.w600,
          letterSpacing: -0.6,
        ),
        headlineSmall: base.textTheme.headlineSmall?.copyWith(
          fontSize: 22,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.4,
        ),
        titleLarge: base.textTheme.titleLarge?.copyWith(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.2,
        ),
        titleMedium: base.textTheme.titleMedium?.copyWith(
          fontSize: 15,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.1,
        ),
        // Inter is drawn for tight spacing; Material's defaults look loose.
        bodyLarge: base.textTheme.bodyLarge?.copyWith(letterSpacing: 0),
        bodyMedium: base.textTheme.bodyMedium?.copyWith(
          height: 1.45,
          letterSpacing: 0,
        ),
        bodySmall: base.textTheme.bodySmall?.copyWith(
          color: CafColors.muted,
          letterSpacing: 0,
        ),
        labelMedium: base.textTheme.labelMedium?.copyWith(letterSpacing: 0),
        labelSmall: base.textTheme.labelSmall?.copyWith(letterSpacing: 0.2),
        labelLarge: base.textTheme.labelLarge?.copyWith(
          fontWeight: FontWeight.w600,
          letterSpacing: 0,
        ),
      )
      .apply(
        fontFamily: _font,
        bodyColor: CafColors.ink,
        displayColor: CafColors.ink,
      );

  final rounded = RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(_radius),
  );
  const buttonSize = Size(64, 44);
  const buttonPadding = EdgeInsets.symmetric(horizontal: 18);
  OutlineInputBorder field(Color color, [double width = 1]) =>
      OutlineInputBorder(
        borderRadius: BorderRadius.circular(_radius),
        borderSide: BorderSide(color: color, width: width),
      );

  return base.copyWith(
    textTheme: text,
    scaffoldBackgroundColor: CafColors.background,
    dividerColor: CafColors.border,
    appBarTheme: AppBarTheme(
      backgroundColor: CafColors.surface,
      foregroundColor: CafColors.ink,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleSpacing: 20,
      toolbarHeight: 60,
      shape: const Border(bottom: BorderSide(color: CafColors.border)),
      titleTextStyle: text.titleMedium?.copyWith(fontSize: 16),
    ),
    cardTheme: CardThemeData(
      color: CafColors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: const EdgeInsets.symmetric(vertical: 5),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: CafColors.border),
      ),
    ),
    dividerTheme: const DividerThemeData(
      color: CafColors.border,
      thickness: 1,
      space: 1,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: CafColors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
      border: field(CafColors.border),
      enabledBorder: field(CafColors.border),
      focusedBorder: field(CafColors.ink, 1.4),
      errorBorder: field(CafColors.error),
      focusedErrorBorder: field(CafColors.error, 1.4),
      disabledBorder: field(CafColors.subtle),
      labelStyle: text.bodyMedium?.copyWith(color: CafColors.muted),
      floatingLabelStyle: text.bodyMedium?.copyWith(color: CafColors.ink),
      hintStyle: text.bodyMedium?.copyWith(color: CafColors.faint),
      helperStyle: text.bodySmall,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: buttonSize,
        padding: buttonPadding,
        shape: rounded,
        textStyle: text.labelLarge,
        disabledBackgroundColor: CafColors.subtle,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        minimumSize: buttonSize,
        padding: buttonPadding,
        shape: rounded,
        elevation: 0,
        backgroundColor: CafColors.surface,
        foregroundColor: CafColors.ink,
        side: const BorderSide(color: CafColors.border),
        textStyle: text.labelLarge,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: buttonSize,
        padding: buttonPadding,
        shape: rounded,
        foregroundColor: CafColors.ink,
        side: const BorderSide(color: CafColors.border),
        textStyle: text.labelLarge,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: CafColors.ink,
        shape: rounded,
        textStyle: text.labelLarge,
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(foregroundColor: CafColors.muted),
    ),
    tabBarTheme: TabBarThemeData(
      labelColor: CafColors.ink,
      unselectedLabelColor: CafColors.muted,
      indicatorColor: CafColors.ink,
      indicatorSize: TabBarIndicatorSize.label,
      dividerColor: CafColors.border,
      tabAlignment: TabAlignment.start,
      labelStyle: text.labelLarge,
      unselectedLabelStyle: text.labelLarge?.copyWith(
        fontWeight: FontWeight.w500,
      ),
      overlayColor: const WidgetStatePropertyAll(Colors.transparent),
    ),
    // Chips are labels (status, counts) or choices (slots, categories): soft
    // pills, never bordered boxes that read as buttons. A chosen one is ink.
    chipTheme: ChipThemeData(
      backgroundColor: CafColors.subtle,
      selectedColor: CafColors.ink,
      disabledColor: CafColors.subtle,
      checkmarkColor: Colors.white,
      side: BorderSide.none,
      shape: const StadiumBorder(),
      padding: const EdgeInsets.symmetric(horizontal: 4),
      labelStyle: text.labelMedium?.copyWith(
        fontSize: 13,
        fontWeight: FontWeight.w500,
        color: CafColors.ink,
      ),
      secondaryLabelStyle: text.labelMedium?.copyWith(
        fontSize: 13,
        fontWeight: FontWeight.w600,
        color: Colors.white,
      ),
    ),
    // List rows share the card titles' type: 15 px semibold, muted subtitle.
    listTileTheme: ListTileThemeData(
      iconColor: CafColors.muted,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16),
      titleTextStyle: text.titleMedium,
      subtitleTextStyle: text.bodyMedium?.copyWith(color: CafColors.muted),
      leadingAndTrailingTextStyle: text.titleMedium?.copyWith(fontSize: 14),
    ),
    expansionTileTheme: const ExpansionTileThemeData(
      shape: Border(),
      collapsedShape: Border(),
      iconColor: CafColors.muted,
      collapsedIconColor: CafColors.muted,
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith(
        (states) => states.contains(WidgetState.selected)
            ? Colors.white
            : CafColors.faint,
      ),
      trackColor: WidgetStateProperty.resolveWith(
        (states) => states.contains(WidgetState.selected)
            ? CafColors.ink
            : CafColors.subtle,
      ),
      trackOutlineColor: WidgetStateProperty.resolveWith(
        (states) => states.contains(WidgetState.selected)
            ? Colors.transparent
            : CafColors.border,
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        backgroundColor: CafColors.surface,
        selectedBackgroundColor: CafColors.ink,
        selectedForegroundColor: Colors.white,
        foregroundColor: CafColors.ink,
        side: const BorderSide(color: CafColors.border),
        shape: rounded,
        textStyle: text.labelLarge?.copyWith(fontWeight: FontWeight.w500),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: CafColors.ink,
      contentTextStyle: text.bodyMedium?.copyWith(color: Colors.white),
      shape: rounded,
      elevation: 0,
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: CafColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      titleTextStyle: text.titleLarge,
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: CafColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(_radius),
        side: const BorderSide(color: CafColors.border),
      ),
      elevation: 2,
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: CafColors.surface,
      surfaceTintColor: Colors.transparent,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: CafColors.ink,
      linearTrackColor: CafColors.subtle,
      circularTrackColor: Colors.transparent,
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(
        color: CafColors.ink,
        borderRadius: BorderRadius.circular(6),
      ),
      textStyle: text.bodySmall?.copyWith(color: Colors.white),
    ),
  );
}

/// Gives a [DropdownButton] the same white, bordered box as the text fields,
/// in place of Material's underline. The dropdown itself is unchanged.
class FieldFrame extends StatelessWidget {
  const FieldFrame({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: CafColors.surface,
        border: Border.all(color: CafColors.border),
        borderRadius: BorderRadius.circular(_radius),
      ),
      child: Padding(
        padding: const EdgeInsets.only(left: 14, right: 8),
        child: DropdownButtonHideUnderline(child: child),
      ),
    );
  }
}
