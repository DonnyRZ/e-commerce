import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/AuthContext";
import { getAdminPushConfig, testAdminPushDevice } from "@/lib/api";
import { cmsServiceWorker, decodePublicKey, isInstalled, isPushAutoEnrollDisabled, matchesPublicKey, pushSupported, registerDeviceSubscription, setPushAutoEnrollDisabled, stopDeviceNotifications } from "./device";

const DeviceContext = createContext(null);

export default function CmsDeviceProvider({ children }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [installed, setInstalled] = useState(isInstalled);
  const [installPrompt, setInstallPrompt] = useState(null);
  const [registered, setRegistered] = useState(false);
  const [autoEnrollDisabled, setAutoEnrollDisabled] = useState(isPushAutoEnrollDisabled);
  const autoEnrollDisabledRef = useRef(autoEnrollDisabled);
  const [permission, setPermission] = useState(() => "Notification" in window ? Notification.permission : "unsupported");
  const [workerError, setWorkerError] = useState(false);
  const config = useQuery({ queryKey: ["admin-push-config", user?.id], queryFn: getAdminPushConfig, enabled: user?.role === "admin", retry: false });

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const resize = () => document.documentElement.style.setProperty("--cms-viewport-height", `${viewport.height}px`);
    resize();
    viewport.addEventListener("resize", resize);
    return () => { viewport.removeEventListener("resize", resize); document.documentElement.style.removeProperty("--cms-viewport-height"); };
  }, []);

  useEffect(() => {
    const capturePrompt = event => { event.preventDefault(); setInstallPrompt(event); };
    const installedEvent = () => { setInstalled(true); setInstallPrompt(null); };
    const display = window.matchMedia("(display-mode: standalone)");
    const refreshDisplay = () => setInstalled(isInstalled());
    window.addEventListener("beforeinstallprompt", capturePrompt);
    window.addEventListener("appinstalled", installedEvent);
    display.addEventListener("change", refreshDisplay);
    cmsServiceWorker().catch(() => setWorkerError(true));
    return () => {
      window.removeEventListener("beforeinstallprompt", capturePrompt);
      window.removeEventListener("appinstalled", installedEvent);
      display.removeEventListener("change", refreshDisplay);
    };
  }, []);

  useEffect(() => {
    let active = true;
    setRegistered(false);
    if (user?.role !== "admin" || !config.data?.enabled || !pushSupported()) return;
    const sync = async () => {
      if (Notification.permission !== "granted") return;
      if (autoEnrollDisabledRef.current || isPushAutoEnrollDisabled()) return;
      const registration = await cmsServiceWorker();
      let subscription = await registration.pushManager.getSubscription();
      if (!active) return;
      if (!matchesPublicKey(subscription, config.data.public_key)) {
        await subscription.unsubscribe();
        subscription = null;
      }
      if (!subscription) subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: decodePublicKey(config.data.public_key) });
      subscription = await registerDeviceSubscription(registration, subscription, config.data.public_key);
      if (active) setRegistered(true);
    };
    sync().catch(() => { if (active) { setRegistered(false); setWorkerError(true); } });
    const refresh = () => {
      setPermission(Notification.permission);
      if (Notification.permission !== "granted") setRegistered(false);
      else sync().catch(() => { if (active) { setRegistered(false); setWorkerError(true); } });
    };
    window.addEventListener("focus", refresh);
    return () => { active = false; window.removeEventListener("focus", refresh); };
  }, [config.data?.enabled, config.data?.public_key, user?.id, user?.role]);

  useEffect(() => {
    if (!("serviceWorker" in navigator) || user?.role !== "admin") return;
    const update = event => {
      if (event.data?.type !== "CMS_PUSH") return;
      for (const key of ["admin-telegram-inbox", "admin-telegram-conversation", "admin-order-workflow", "admin-dashboard"])
        queryClient.invalidateQueries({ queryKey: [key] });
    };
    navigator.serviceWorker.addEventListener("message", update);
    return () => navigator.serviceWorker.removeEventListener("message", update);
  }, [queryClient, user?.role]);

  const value = {
    installed, installAvailable: Boolean(installPrompt), registered, permission, workerError, autoEnrollDisabled,
    supported: pushSupported(), config,
    async install() {
      if (!installPrompt) return "unavailable";
      await installPrompt.prompt();
      const choice = await installPrompt.userChoice;
      setInstallPrompt(null);
      return choice.outcome;
    },
    async enable() {
      if (!pushSupported() || !config.data?.enabled) throw new Error("push_unavailable");
      // Request permission directly from the button gesture, before waiting for the worker.
      const granted = await Notification.requestPermission();
      setPermission(granted);
      if (granted !== "granted") return false;
      setPushAutoEnrollDisabled(false);
      autoEnrollDisabledRef.current = false;
      setAutoEnrollDisabled(false);
      const registration = await cmsServiceWorker();
      let subscription = await registration.pushManager.getSubscription();
      if (subscription && !matchesPublicKey(subscription, config.data.public_key)) {
        await subscription.unsubscribe();
        subscription = null;
      }
      if (!subscription) subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: decodePublicKey(config.data.public_key) });
      await registerDeviceSubscription(registration, subscription, config.data.public_key);
      setRegistered(true);
      setWorkerError(false);
      return true;
    },
    async disable() {
      setPushAutoEnrollDisabled(true);
      autoEnrollDisabledRef.current = true;
      setAutoEnrollDisabled(true);
      try { await stopDeviceNotifications(); } finally { setRegistered(false); }
    },
    async test() {
      const subscription = await (await cmsServiceWorker()).pushManager.getSubscription();
      if (!subscription) throw new Error("push_unavailable");
      return testAdminPushDevice(subscription.endpoint);
    },
  };
  return <DeviceContext.Provider value={value}>{children}</DeviceContext.Provider>;
}

export const useCmsDevice = () => useContext(DeviceContext);
