import { Outlet } from "react-router-dom";
import AnnouncementBar from "./AnnouncementBar";
import Header from "./Header";
import Footer from "./Footer";

export default function AppShell() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <AnnouncementBar />
      <Header />
      <main
        data-testid="main-content"
        className="mx-auto w-full max-w-[1440px] flex-1 px-4 sm:px-6 lg:px-10"
      >
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
