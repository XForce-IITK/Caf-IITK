import 'package:flutter/material.dart';

import 'theme.dart';

/// The Caf@IITK mark: a small accent tile with a cup, then the name.
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 28, this.showName = true});

  final double size;
  final bool showName;

  @override
  Widget build(BuildContext context) {
    final tile = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: CafColors.accent,
        borderRadius: BorderRadius.circular(size * 0.28),
      ),
      child: Icon(
        Icons.local_cafe_outlined,
        size: size * 0.58,
        color: Colors.white,
      ),
    );
    if (!showName) return ExcludeSemantics(child: tile);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        ExcludeSemantics(child: tile),
        SizedBox(width: size * 0.36),
        Text(
          'Caf@IITK',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontSize: size * 0.6,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
          ),
        ),
      ],
    );
  }
}
