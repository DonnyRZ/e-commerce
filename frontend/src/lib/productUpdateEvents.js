const CHANNEL_NAME = "muslimah-cantik:product-updates";
const STORAGE_KEY = "muslimah-cantik:product-update";

let channel;
const listeners = new Set();

const deliver = (event) => {
  const update = event?.data;
  if (!update || update.type !== "product-updated") return;
  listeners.forEach((listener) => listener(update));
};

const getChannel = () => {
  if (typeof BroadcastChannel === "undefined") return null;
  if (!channel) {
    try {
      channel = new BroadcastChannel(CHANNEL_NAME);
      channel.addEventListener("message", deliver);
    } catch {
      return null;
    }
  }
  return channel;
};

export const announceProductUpdate = (productId, revision) => {
  if (!productId) return;
  const update = {
    type: "product-updated",
    productId,
    revision: Number(revision) || null,
    sentAt: Date.now(),
  };
  const activeChannel = getChannel();
  if (activeChannel) {
    activeChannel.postMessage(update);
  } else {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(update));
    } catch {
      // Storage and BroadcastChannel may both be blocked; focus refetch still covers the store detail.
    }
  }
};

export const subscribeToProductUpdates = (listener) => {
  listeners.add(listener);
  getChannel();

  const onStorage = (event) => {
    if (event.key !== STORAGE_KEY || !event.newValue) return;
    try {
      deliver({ data: JSON.parse(event.newValue) });
    } catch {
      // Ignore malformed cross-tab signals; the next server refetch is authoritative.
    }
  };
  if (typeof window !== "undefined") window.addEventListener("storage", onStorage);

  return () => {
    listeners.delete(listener);
    if (typeof window !== "undefined") window.removeEventListener("storage", onStorage);
  };
};
