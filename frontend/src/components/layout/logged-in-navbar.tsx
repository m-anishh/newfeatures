"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { 
  Shield, LayoutDashboard, Upload, 
  FileText, Activity, Settings, LogOut, User as UserIcon,
  ChevronDown
} from "lucide-react";
import type { User } from "@/lib/auth-session";

interface LoggedInNavbarProps {
  user: User;
}

export function LoggedInNavbar({ user }: LoggedInNavbarProps) {
  const pathname = usePathname();
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  React.useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const { signOut } = useAuth();

  const handleLogout = async () => {
    await signOut();
    window.location.href = "/";
  };

  const isActive = (path: string) => {
    if (path === "/") return pathname === "/";
    return pathname.startsWith(path);
  };

  return (
    <nav className="sticky top-0 z-50 bg-surface border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
              <Shield className="w-4 h-4 text-white" />
            </div>
            <span className="text-lg font-bold text-text tracking-tight">
              Vision<span className="text-primary">X</span>
            </span>
          </Link>

          {/* Desktop Nav */}
          <div className="hidden md:flex items-center gap-1">
            {[
              { href: "/dashboard", label: "Dashboard" },
              { href: "/analyze", label: "Analyze" },
              { href: "/reports", label: "Reports" },
              { href: "/history", label: "History" },
              { href: "/incidents", label: "Incidents" },
            ].map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                  isActive(link.href)
                    ? "text-primary bg-primary-50"
                    : "text-muted hover:text-text hover:bg-background"
                }`}
              >
                {link.label}
              </Link>
            ))}
          </div>

          {/* Auth Section */}
          <div className="hidden md:flex items-center gap-3">
            <div className="relative">
              <button
                onClick={() => setProfileMenuOpen(!profileMenuOpen)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-background transition-colors"
                aria-label="Profile menu"
              >
                <Avatar
                  name={user.user_metadata?.full_name || user.email || "U"}
                  size="sm"
                />
                <span className="text-sm font-medium text-text max-w-[120px] truncate">
                  {user.user_metadata?.full_name || user.email?.split("@")[0] || "User"}
                </span>
                <ChevronDown className="w-4 h-4 text-muted" />
              </button>

              {profileMenuOpen && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setProfileMenuOpen(false)}
                  />
                  <div className="absolute right-0 mt-2 w-48 bg-surface border border-border rounded-lg shadow-md z-20 py-1">
                    <Link
                      href="/profile"
                      className="flex items-center gap-2 px-4 py-2 text-sm text-text hover:bg-background transition-colors"
                      onClick={() => setProfileMenuOpen(false)}
                    >
                      <UserIcon className="w-4 h-4" />
                      Profile
                    </Link>
                    <Link
                      href="/settings"
                      className="flex items-center gap-2 px-4 py-2 text-sm text-text hover:bg-background transition-colors"
                      onClick={() => setProfileMenuOpen(false)}
                    >
                      <Settings className="w-4 h-4" />
                      Settings
                    </Link>
                    <hr className="border-border my-1" />
                    <button
                      onClick={() => {
                        setProfileMenuOpen(false);
                        handleLogout();
                      }}
                      className="flex items-center gap-2 px-4 py-2 text-sm text-danger hover:bg-background w-full transition-colors"
                    >
                      <LogOut className="w-4 h-4" />
                      Sign Out
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Menu - simplified for brevity */}
    </nav>
  );
}