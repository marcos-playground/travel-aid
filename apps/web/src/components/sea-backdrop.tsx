const WIDTH = 1200;
const HEIGHT = 240;

// Gentle swells drawn as sine lines, lower rows slightly out of phase with the ones above.
const WAVES = Array.from({ length: 7 }, (_, row) => {
  const y = 70 + row * 26;
  const points: string[] = [];
  for (let x = 0; x <= WIDTH; x += 12) {
    points.push(`${x},${(y + Math.sin(x / 42 + row * 1.3) * 5).toFixed(1)}`);
  }
  return `M${points.join(" L")}`;
});

/** Decorative sea surface and sun glow behind the hero. */
export function SeaBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      <div className="absolute -top-24 right-[4%] size-80 rounded-full bg-[radial-gradient(closest-side,rgb(255_210_63/0.55),transparent)]" />
      <svg
        className="absolute inset-x-0 bottom-0 h-3/5 w-full"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="none"
      >
        {WAVES.map((d) => (
          <path key={d} d={d} fill="none" stroke="white" strokeOpacity={0.14} strokeWidth={2} vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
    </div>
  );
}
