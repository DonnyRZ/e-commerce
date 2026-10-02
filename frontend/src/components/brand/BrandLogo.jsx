import { Link } from "react-router-dom";

const MARK_SOURCES = {
  sm: { src: "/brand/logo-mark-64.png", px: 64 },
  md: { src: "/brand/logo-mark-128.png", px: 128 },
  lg: { src: "/brand/logo-mark-256.png", px: 256 },
};

const SIZE_STYLES = {
  sm: {
    mark: "h-8 w-8",
    lockup: "gap-2",
    wordmark: "text-[0.62rem] tracking-[0.16em] sm:text-[0.7rem]",
  },
  md: {
    mark: "h-8 w-8 sm:h-10 sm:w-10",
    lockup: "gap-2 sm:gap-2.5",
    wordmark: "text-[0.62rem] tracking-[0.14em] sm:text-[0.82rem] sm:tracking-[0.18em]",
  },
  lg: {
    mark: "h-16 w-16",
    lockup: "gap-4",
    wordmark: "text-xl tracking-[0.2em] sm:text-2xl",
  },
};

const assetBase = (process.env.PUBLIC_URL || "").replace(/\/$/, "");

const assetPath = (path) => `${assetBase}${path}`;

export default function BrandLogo({
  variant = "full",
  size = "md",
  to = "/",
  className = "",
  wordmarkClassName = "",
  testId = "brand-logo",
  priority = false,
}) {
  const source = MARK_SOURCES[size] || MARK_SOURCES.md;
  const styles = SIZE_STYLES[size] || SIZE_STYLES.md;
  const isMarkOnly = variant === "mark";
  const label = "MUSLIMAH CANTIK";

  const content = (
    <span
      className={`inline-flex min-w-0 items-center ${styles.lockup} ${className}`}
    >
      <img
        src={assetPath(source.src)}
        width={source.px}
        height={source.px}
        alt={isMarkOnly && !to ? label : ""}
        aria-hidden={isMarkOnly && !to ? undefined : true}
        loading={priority ? "eager" : "lazy"}
        fetchPriority={priority ? "high" : "auto"}
        draggable="false"
        className={`${styles.mark} shrink-0 object-contain`}
      />
      {!isMarkOnly ? (
        <span className={`brand-wordmark min-w-0 whitespace-nowrap font-brand font-semibold leading-none text-brand-forest ${styles.wordmark} ${wordmarkClassName}`}>
          {label}
        </span>
      ) : null}
    </span>
  );

  if (!to) {
    return (
      <span data-testid={testId} className="inline-flex min-w-0">
        {content}
      </span>
    );
  }

  return (
    <Link to={to} aria-label={label} className="inline-flex min-w-0" data-testid={testId}>
      {content}
    </Link>
  );
}
