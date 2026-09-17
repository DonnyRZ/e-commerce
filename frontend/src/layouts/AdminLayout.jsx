import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  ClipboardList,
  FileText,
  FolderTree,
  Image,
  LayoutDashboard,
  Menu,
  Package,
  Settings,
  ShieldAlert,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import BrandLogo from "@/components/brand/BrandLogo";

function NavItem({ to, icon: Icon, label, end, onClick, testId }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      data-testid={testId}
      className={({ isActive }) =>
        `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
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

function NavGroup({ label }) {
  return (
    <p className="px-4 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-widest text-neutral-400">
      {label}
    </p>
  );
}

export default function AdminLayout() {
  const { user } = useAuth();
  const [drawer, setDrawer] = useState(false);

  const nav = (onClick) => (
    <nav className="flex flex-col py-4">
      <NavItem to="/" end icon={LayoutDashboard} label="Dashboard" onClick={onClick} testId="admin-nav-dashboard" />
      <NavGroup label="Catalog" />
      <NavItem to="/products" icon={Package} label="Products" onClick={onClick} testId="admin-nav-products" />
      <NavItem to="/categories" icon={FolderTree} label="Categories" onClick={onClick} testId="admin-nav-categories" />
      <NavGroup label="Sales" />
      <NavItem to="/orders" icon={ClipboardList} label="Orders" onClick={onClick} testId="admin-nav-orders" />
      <NavItem to="/payments" icon={ShieldAlert} label="Payment Review" onClick={onClick} testId="admin-nav-payments" />
      <NavItem to="/customers" icon={Users} label="Customers" onClick={onClick} testId="admin-nav-customers" />
      <NavGroup label="CMS" />
      <NavItem to="/cms" icon={FileText} label="Konten" onClick={onClick} testId="admin-nav-cms" />
      <NavItem to="/media" icon={Image} label="Pustaka Media" onClick={onClick} testId="admin-nav-media" />
      <NavGroup label="System" />
      <NavItem to="/settings" icon={Settings} label="Settings" onClick={onClick} testId="admin-nav-settings" />
    </nav>
  );

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900" data-testid="admin-layout">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-neutral-200 bg-white px-4 lg:px-6">
        <button
          className="lg:hidden"
          onClick={() => setDrawer(true)}
          aria-label="menu"
          data-testid="admin-menu-open"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          <BrandLogo size="sm" to="/" testId="admin-brand" priority />
          <span className="text-xs font-medium text-neutral-400">Admin</span>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <a href="/" className="text-xs text-neutral-500 hover:text-neutral-900" data-testid="admin-view-store">
            View Store
          </a>
          <span className="hidden text-xs text-neutral-400 sm:block" data-testid="admin-user-email">
            {user.email}
          </span>
        </div>
      </header>

      <div className="flex">
        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-56 shrink-0 border-r border-neutral-200 bg-white lg:block">
          {nav()}
        </aside>
        {drawer ? (
          <div className="fixed inset-0 z-40 lg:hidden" data-testid="admin-drawer">
            <div className="absolute inset-0 bg-black/30" onClick={() => setDrawer(false)} />
            <aside className="absolute left-0 top-0 h-full w-64 bg-white shadow-lg">
              <div className="flex h-14 items-center justify-between border-b border-neutral-200 px-4">
                <span className="text-sm font-bold">Admin</span>
                <button onClick={() => setDrawer(false)} aria-label="close" data-testid="admin-menu-close">
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
