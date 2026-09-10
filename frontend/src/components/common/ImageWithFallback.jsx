const FALLBACK_SRC = "/image-placeholder.svg";

export default function ImageWithFallback({ src, alt, onError, ...props }) {
  const handleError = (event) => {
    if (event.currentTarget.dataset.fallbackApplied) return;
    event.currentTarget.dataset.fallbackApplied = "true";
    event.currentTarget.src = FALLBACK_SRC;
    onError?.(event);
  };

  return (
    <img
      src={src || FALLBACK_SRC}
      alt={alt || ""}
      onError={handleError}
      {...props}
    />
  );
}
