import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  ClipboardList,
  MessageCircle,
  FileText,
  FolderTree,
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  Settings,
  Store,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { useI18n } from "@/i18n";
import BrandLogo from "@/components/brand/BrandLogo";

function NavItem({ to, icon: Icon, label, end, onClick, testId }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      data-testid={testId}
      className={({ isActive }) =>
        `flex min-h-11 items-center gap-3 px-4 py-3 text-sm transition-colors ${
          isActive
            ? "border-r-2 border-[#145A46] bg-[#145A46]/5 font-semibold text-[#145A46]"
            : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900"
        }`
      }
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </NavLink>
  );
}

function CmsSubNavItem({ to, label, onClick, testId }) {
  return (
    <NavLink
      to={to}
      end
      onClick={onClick}
      data-testid={testId}
      className={({ isActive }) =>
        `ml-8 flex min-h-10 items-center border-l px-4 py-2.5 text-xs transition-colors ${
          isActive
            ? "border-[#145A46] font-semibold text-[#145A46]"
            : "border-neutral-200 text-neutral-500 hover:border-neutral-400 hover:text-neutral-900"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

function NavGroup({ label }) {
  return (
    <p className="px-4 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-widest text-neutral-400">
      {label}
    </p>
  );
}

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const [drawer, setDrawer] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
    }
  };

  const nav = (onClick) => (
    <nav className="flex flex-col py-2">
      <NavItem to="/" end icon={LayoutDashboard} label="Dashboard" onClick={onClick} testId="admin-nav-dashboard" />
      <NavGroup label="Catalog" />
      <NavItem to="/products" icon={Package} label="Products" onClick={onClick} testId="admin-nav-products" />
      <NavItem to="/categories" icon={FolderTree} label="Categories" onClick={onClick} testId="admin-nav-categories" />
      <NavGroup label="Sales" />
      <NavItem to="/orders" icon={ClipboardList} label="Orders" onClick={onClick} testId="admin-nav-orders" />
      <NavItem to="/telegram-inbox" icon={MessageCircle} label="Inbox Telegram" onClick={onClick} testId="admin-nav-telegram-inbox" />
      <NavItem to="/customers" icon={Users} label="Customers" onClick={onClick} testId="admin-nav-customers" />
      <NavGroup label="CMS" />
      <NavItem to="/cms" icon={FileText} label="Konten" onClick={onClick} testId="admin-nav-cms" />
      <CmsSubNavItem to="/cms/homepage" label="Homepage" onClick={onClick} testId="admin-nav-cms-homepage" />
      <CmsSubNavItem to="/cms/stories" label="Stories & Editorial" onClick={onClick} testId="admin-nav-cms-stories" />
      <CmsSubNavItem to="/cms/help" label="FAQ & Halaman informasi" onClick={onClick} testId="admin-nav-cms-help" />
      <CmsSubNavItem to="/cms/navigation" label="Navigasi & Footer" onClick={onClick} testId="admin-nav-cms-navigation" />
      <CmsSubNavItem to="/media" label="Pustaka Media" onClick={onClick} testId="admin-nav-media" />
      <NavGroup label="System" />
      <NavItem to="/settings" icon={Settings} label="Settings" onClick={onClick} testId="admin-nav-settings" />
    </nav>
  );

  return (
    <div className="min-h-dvh bg-neutral-50 text-neutral-900" data-testid="admin-layout">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-neutral-200 bg-white px-2 sm:gap-3 sm:px-4 lg:px-6">
        <button
          className="inline-flex h-10 w-10 shrink-0 items-center justify-center lg:hidden"
          onClick={() => setDrawer(true)}
          aria-label="Buka menu navigasi CMS"
          aria-expanded={drawer}
          aria-controls="admin-mobile-drawer"
          data-testid="admin-menu-open"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex min-w-0 items-center gap-2">
          <BrandLogo size="sm" to="/" wordmarkClassName="hidden sm:inline" testId="admin-brand" priority />
          <span className="hidden text-xs font-medium text-neutral-400 sm:inline">Admin</span>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-3">
          <a href="/" aria-label="Lihat toko" title="Lihat toko" className="inline-flex h-10 w-10 items-center justify-center text-xs text-neutral-500 hover:text-neutral-900 sm:h-auto sm:w-auto sm:justify-start" data-testid="admin-view-store">
            <Store className="h-4 w-4 sm:hidden" aria-hidden="true" />
            <span className="hidden whitespace-nowrap sm:inline">View Store</span>
          </a>
          <span className="hidden text-xs text-neutral-400 sm:block" data-testid="admin-user-email">
            {user.email}
          </span>
          <button
            type="button"
            onClick={handleLogout}
            disabled={loggingOut}
            data-testid="admin-logout"
            aria-label={loggingOut ? t("common.loading") : t("auth.logout")}
            title={loggingOut ? t("common.loading") : t("auth.logout")}
            className="inline-flex h-10 w-10 items-center justify-center gap-1.5 border border-neutral-200 px-0 text-xs font-medium text-neutral-600 transition-colors hover:border-neutral-900 hover:text-neutral-900 disabled:cursor-wait disabled:opacity-50 sm:w-auto sm:px-2.5"
          >
            <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden whitespace-nowrap sm:inline">{loggingOut ? t("common.loading") : t("auth.logout")}</span>
          </button>
        </div>
      </header>

      <div className="flex">
        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-56 shrink-0 overflow-y-auto overscroll-contain border-r border-neutral-200 bg-white lg:block">
          {nav()}
        </aside>
        {drawer ? (
          <div className="fixed inset-0 z-40 lg:hidden" data-testid="admin-drawer">
            <button type="button" className="absolute inset-0 bg-black/30" onClick={() => setDrawer(false)} aria-label="Tutup menu navigasi CMS" />
            <aside id="admin-mobile-drawer" aria-label="Navigasi CMS" className="absolute inset-y-0 left-0 flex h-dvh max-h-dvh w-64 flex-col overflow-y-auto overscroll-contain bg-white pb-[env(safe-area-inset-bottom)] shadow-lg">
              <div className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-4">
                <span className="text-sm font-bold">Admin</span>
                <button className="inline-flex h-11 w-11 items-center justify-center" onClick={() => setDrawer(false)} aria-label="Tutup menu" data-testid="admin-menu-close">
                  <X className="h-5 w-5" />
                </button>
              </div>
              {nav(() => setDrawer(false))}
            </aside>
          </div>
        ) : null}
        <main className="min-w-0 flex-1 p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
