import { useState } from "react";

const FALLBACK_SRC = "/image-placeholder.svg";

export default function ImageWithFallback({ src, alt, onError, ...props }) {
  const requestedSrc = typeof src === "string" && src.trim() ? src : FALLBACK_SRC;
  const [failedSrc, setFailedSrc] = useState(null);
  const displayedSrc = failedSrc === requestedSrc ? FALLBACK_SRC : requestedSrc;

  const handleError = (event) => {
    if (failedSrc === requestedSrc) return;
    setFailedSrc(requestedSrc);
    onError?.(event);
  };

  return (
    <img
      src={displayedSrc}
      alt={alt || ""}
      onError={handleError}
      {...props}
    />
  );
}
