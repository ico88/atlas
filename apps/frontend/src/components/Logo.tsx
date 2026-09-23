/**
 * ATLAS brand mark — an SVG recreation of the logo (network ring + gradient "A").
 * Uses currentColor for the ring/nodes so it adapts to the surrounding text
 * color; the "A" carries the DwarfStar solar-yellow brand accent. Swap for the
 * official asset when available.
 */
export default function Logo({ size = 34 }: { size?: number }) {
  const nodes: [number, number][] = [
    [58, 32],
    [50.4, 13.6],
    [32, 6],
    [13.6, 13.6],
    [6, 32],
    [13.6, 50.4],
    [32, 58],
    [50.4, 50.4],
  ];
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="atlasGrad" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#e8a600" />
          <stop offset="1" stopColor="#ffc400" />
        </linearGradient>
      </defs>
      <circle
        cx="32"
        cy="32"
        r="26"
        stroke="currentColor"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
      {nodes.map(([x, y], i) => (
        <line
          key={`l-${i}`}
          x1="32"
          y1="32"
          x2={x}
          y2={y}
          stroke="currentColor"
          strokeOpacity="0.18"
          strokeWidth="1"
        />
      ))}
      {nodes.map(([x, y], i) => (
        <circle
          key={`n-${i}`}
          cx={x}
          cy={y}
          r={i % 2 === 0 ? 3 : 2.2}
          fill="currentColor"
          fillOpacity={i % 2 === 0 ? 0.9 : 0.5}
        />
      ))}
      <path
        d="M19 45 L32 19 L45 45"
        stroke="url(#atlasGrad)"
        strokeWidth="4.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M24.5 38 L39.5 38"
        stroke="url(#atlasGrad)"
        strokeWidth="4.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
