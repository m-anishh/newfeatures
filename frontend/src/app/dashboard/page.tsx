"use client";

import React, { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { Navbar } from "@/components/layout/navbar";
import { Footer } from "@/components/layout/footer";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useAuth } from "@/lib/auth-context";
import { apiClient } from "@/lib/api-client";
import {
  BarChart3, FileText, AlertTriangle, Shield, Activity, Download,
  Clock, CheckCircle2, Search, Upload, Settings, Server, HardDrive,
  ArrowRight, ShieldAlert, Sparkles, Image, Scan, Camera,
  Layers, RefreshCw, DownloadCloud,
  Bot, Cpu,
  LineChart as LineChartIcon, PieChart as PieChartIcon,
} from "lucide-react";
import {
  AreaChart as RechartsArea, Area,
  PieChart as RechartsPie, Pie, Cell, ResponsiveContainer,
  XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
} from "recharts";

// ─────────────────────────────────────────
// Color palette — modern white & blue system.
// Blue carries the interface chrome (structure, icons, charts).
// Green / amber / red are reserved strictly for real status meaning
// (authentic / needs review / risk) so they stay meaningful, not decorative.
// ─────────────────────────────────────────
const COLORS = {
  primary: "#2563EB",     // blue-600 — core brand / primary data
  secondary: "#3B82F6",   // blue-500
  sky: "#0EA5E9",         // sky-500 — secondary blue accent
  cyan: "#0891B2",        // cyan-600 — tertiary blue accent
  indigo: "#4F46E5",      // indigo-600 — blue-violet accent, still "blue family"
  navy: "#1E3A8A",        // blue-900 — deep accent for emphasis
  primaryLight: "#DBEAFE",
  success: "#22C55E",     // status only: healthy / authentic
  warning: "#F59E0B",     // status only: needs verification
  danger: "#EF4444",      // status only: risk / manipulated
  surface: "#F8FAFC",
  border: "#E2E8F0",
  text: "#0F172A",
  muted: "#64748B",
};

// ─────────────────────────────────────────
// Types
// ─────────────────────────────────────────
interface DashboardData {
  total_analyses: number;
  completed_reports: number;
  average_trust_score: number;
  trust_distribution: Record<string, number>;
  total_scans?: number;
  completed_analyses?: number;
  processing_analyses?: number;
  failed_analyses?: number;
  total_incidents?: number;
  risk_distribution?: Record<string, number>;
  recent_scans?: unknown[];
  running_jobs?: number;
  completed_jobs?: number;
}

interface Incident {
  id?: string;
  reason?: string;
  title?: string;
  created_at?: string;
  trust_score?: number;
}

interface Report {
  id?: string;
  title?: string;
  trust_score?: number;
  created_at?: string;
  pdf_url?: string;
}

// ─────────────────────────────────────────
// Agents — all rendered in blue-family tints so the pipeline
// reads as one coherent system rather than a rainbow of modules.
// ─────────────────────────────────────────
const AGENTS = [
  { id: "image_analysis", name: "Image Analysis", icon: Image, color: COLORS.primary, desc: "Resolution, blur, noise detection" },
  { id: "metadata", name: "Metadata", icon: Camera, color: COLORS.sky, desc: "EXIF & file metadata extraction" },
  { id: "ocr", name: "OCR", icon: Scan, color: COLORS.cyan, desc: "Text extraction & recognition" },
  { id: "gemini_reasoning", name: "Gemini AI", icon: Bot, color: COLORS.indigo, desc: "AI-powered reasoning & analysis" },
  { id: "manager_decision", name: "Decision Engine", icon: Layers, color: COLORS.navy, desc: "Evidence fusion & scoring" },
  { id: "report", name: "Report", icon: FileText, color: COLORS.secondary, desc: "PDF generation & storage" },
];

export default function DashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [reports, setReports] = useState<Report[]>([]);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    try {
      const [dashRes, incRes, repRes] = await Promise.all([
        apiClient.getDashboardStats(),
        apiClient.getIncidents({ limit: 5 }).catch(() => ({ incidents: [] })),
        apiClient.getReports({ limit: 5 }).catch(() => ({ reports: [] })),
      ]);

      const s = dashRes.stats || {};
      setData({
        total_analyses: s.total_scans || s.total_analyses || 0,
        completed_reports: s.total_reports || 0,
        average_trust_score: s.average_trust_score || 0,
        trust_distribution: s.trust_distribution || { likely_authentic: 0, mostly_authentic: 0, needs_verification: 0, likely_manipulated: 0 },
        total_scans: s.total_scans || 0,
        completed_analyses: s.completed_analyses || 0,
        processing_analyses: s.processing_analyses || 0,
        failed_analyses: s.failed_analyses || 0,
        total_incidents: s.total_incidents || 0,
        risk_distribution: s.risk_distribution || {},
        recent_scans: s.recent_scans || [],
        running_jobs: s.running_jobs || 0,
        completed_jobs: s.completed_jobs || 0,
      });
      setIncidents(incRes.incidents || []);
      setReports(repRes.reports || []);
    } catch (e) {
      console.error("Dashboard load error:", e);
    } finally {
      setLoading(false);
    }
  };

  // ── Chart data ──
  const trustTrendData = useMemo(() => {
    const scans = data?.recent_scans || [];
    return scans.slice(0, 10).reverse().map((s: unknown, i: number) => {
      const scan = s as Record<string, unknown>;
      return {
        name: `#${i + 1}`,
        trust: (scan.trust_score as number) ?? 0,
      };
    });
  }, [data]);

  const riskData = useMemo(() => {
    const rd = data?.trust_distribution || {};
    return [
      { name: "Likely Authentic", value: rd.likely_authentic || 0, color: COLORS.primary },
      { name: "Mostly Authentic", value: rd.mostly_authentic || 0, color: COLORS.sky },
      { name: "Needs Verification", value: rd.needs_verification || 0, color: COLORS.warning },
      { name: "Likely Manipulated", value: rd.likely_manipulated || 0, color: COLORS.danger },
    ].filter(d => d.value > 0);
  }, [data]);

  const scans = data?.recent_scans || [];

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50">
        <Navbar />
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="card p-4 animate-pulse bg-white rounded-2xl border border-blue-100">
                <div className="skeleton h-4 w-24 rounded mb-3 bg-blue-50" />
                <div className="skeleton h-8 w-16 rounded mb-2 bg-blue-50" />
                <div className="skeleton h-3 w-20 rounded bg-blue-50" />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="card p-6 animate-pulse bg-white rounded-2xl border border-blue-100">
                <div className="skeleton h-64 w-full rounded bg-blue-50" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const avgScore = data?.average_trust_score ?? 0;
  const userName = user?.user_metadata?.full_name || user?.email?.split("@")[0] || "Analyst";

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />

      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-6 lg:py-8">

        {/* ──────── HEADER ──────── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-8 gap-4 rounded-2xl bg-gradient-to-r from-blue-600 to-blue-500 p-6 shadow-sm shadow-blue-200">
          <div>
            <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight">
              VisionX Dashboard
            </h1>
            <p className="text-blue-100 mt-1 flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-white animate-pulse" />
              Welcome back, <span className="font-medium text-white">{userName}</span>
              <span className="hidden sm:inline">· {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}</span>
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="secondary" size="sm" onClick={loadAll} className="gap-2 rounded-xl bg-white/15 border-white/30 text-white hover:bg-white/25">
              <RefreshCw className="w-4 h-4" /> Refresh
            </Button>
            <Link href="/analyze">
              <Button size="sm" className="gap-2 rounded-xl bg-white text-blue-600 hover:bg-blue-50 shadow-sm">
                <Upload className="w-4 h-4" /> Upload & Analyze
              </Button>
            </Link>
          </div>
        </div>

        {/* ──────── STATS CARDS (5) ──────── */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
          <StatCard
            icon={<BarChart3 className="w-5 h-5" />}
            label="Total Analyses"
            value={data?.total_analyses ?? 0}
            trend={data?.completed_analyses ? `${((data.completed_analyses! / (data.total_analyses || 1)) * 100).toFixed(0)}%` : "0%"}
            trendLabel="completion"
            gradient="from-blue-500 to-blue-600"
            delay={0}
          />
          <StatCard
            icon={<CheckCircle2 className="w-5 h-5" />}
            label="Completed"
            value={data?.completed_analyses ?? 0}
            trend={data?.processing_analyses ? `${data.processing_analyses} running` : "Idle"}
            trendLabel="now"
            gradient="from-sky-400 to-sky-500"
            delay={1}
          />
          <StatCard
            icon={<Shield className="w-5 h-5" />}
            label="Avg Trust Score"
            value={`${avgScore}%`}
            trend={avgScore >= 60 ? "Healthy" : avgScore >= 40 ? "Moderate" : "Critical"}
            trendLabel="status"
            gradient="from-indigo-500 to-blue-700"
            delay={2}
          />
          <StatCard
            icon={<ShieldAlert className="w-5 h-5" />}
            label="High Risk Incidents"
            value={data?.total_incidents ?? 0}
            trend="Auto-detected"
            trendLabel="source"
            gradient="from-rose-500 to-rose-600"
            delay={3}
          />
          <StatCard
            icon={<FileText className="w-5 h-5" />}
            label="Reports Generated"
            value={data?.completed_reports ?? 0}
            trend={data?.completed_reports ? `${data.completed_reports} total` : "No reports"}
            trendLabel="generated"
            gradient="from-cyan-500 to-blue-500"
            delay={4}
          />
        </div>

        {/* ──────── CHARTS ROW ──────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Trust Score Trend */}
          <Card className="lg:col-span-2 rounded-2xl border-blue-100 shadow-sm bg-white">
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
                    <LineChartIcon className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-800">Trust Score Trend</h3>
                    <p className="text-xs text-slate-400">Last {trustTrendData.length} analyses</p>
                  </div>
                </div>
                <Badge className="bg-blue-50 text-blue-700 border-blue-200 rounded-lg">
                  Avg {avgScore}%
                </Badge>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <RechartsArea data={trustTrendData.length ? trustTrendData : [{ name: "No data", trust: 0 }]}>
                    <defs>
                      <linearGradient id="trustGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.25} />
                        <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
                    <RechartsTooltip
                      contentStyle={{
                        borderRadius: 12,
                        border: "1px solid #E2E8F0",
                        boxShadow: "0 4px 12px rgba(37,99,235,0.10)",
                        background: "white",
                      }}
                      formatter={(v: unknown) => [`${v ?? 0}%`, "Trust Score"]}
                    />
                    <Area type="monotone" dataKey="trust" stroke={COLORS.primary} strokeWidth={2.5} fill="url(#trustGrad)" dot={{ r: 3, fill: COLORS.primary, stroke: "white", strokeWidth: 2 }} />
                  </RechartsArea>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          {/* Risk Distribution Donut */}
          <Card className="rounded-2xl border-blue-100 shadow-sm bg-white">
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
                    <PieChartIcon className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-800">Risk Distribution</h3>
                    <p className="text-xs text-slate-400">Trust classification</p>
                  </div>
                </div>
              </div>
              <div className="h-56 flex items-center justify-center">
                {riskData.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <RechartsPie>
                      <Pie
                        data={riskData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={85}
                        paddingAngle={3}
                        dataKey="value"
                      >
                        {riskData.map((entry, i) => (
                          <Cell key={i} fill={entry.color} stroke="white" strokeWidth={2} />
                        ))}
                      </Pie>
                      <RechartsTooltip
                        contentStyle={{
                          borderRadius: 12,
                          border: "1px solid #E2E8F0",
                          background: "white",
                        }}
                        formatter={(value: unknown, name: unknown) => {
                          const val = value as number;
                          return [`${val}%`, name as string];
                        }}
                      />
                    </RechartsPie>
                  </ResponsiveContainer>
                ) : (
                  <div className="text-center text-slate-400">
                    <PieChartIcon className="w-12 h-12 mx-auto mb-2 opacity-40" />
                    <p className="text-sm">No distribution data</p>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 mt-2">
                {riskData.map((d, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: d.color }} />
                    <span className="text-slate-500 truncate">{d.name}</span>
                    <span className="font-medium text-slate-700 ml-auto">{d.value}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ──────── AI AGENTS + ACTIVITY ──────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* AI Agent Status */}
          <Card className="rounded-2xl border-blue-100 shadow-sm bg-white lg:col-span-1">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
                  <Bot className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-800">AI Agent Pipeline</h3>
                  <p className="text-xs text-slate-400">Real-time agent status</p>
                </div>
              </div>
              <div className="space-y-2.5">
                {AGENTS.map((agent, i) => (
                  <AgentRow key={agent.id} agent={agent} index={i} />
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Activity Timeline + Quick Actions */}
          <div className="lg:col-span-2 space-y-6">
            {/* Recent Scans Table */}
            <Card className="rounded-2xl border-blue-100 shadow-sm bg-white">
              <CardContent className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
                      <Activity className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-slate-800">Recent Analyses</h3>
                      <p className="text-xs text-slate-400">Latest scan results</p>
                    </div>
                  </div>
                  <Link href="/history/uploads">
                    <Button variant="ghost" size="sm" className="gap-1 text-xs text-blue-600">
                      View All <ArrowRight className="w-3 h-3" />
                    </Button>
                  </Link>
                </div>
                {scans.length ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-blue-50">
                          <th className="text-left font-medium text-slate-400 pb-2 pr-4">File</th>
                          <th className="text-left font-medium text-slate-400 pb-2 pr-4 hidden sm:table-cell">Date</th>
                          <th className="text-left font-medium text-slate-400 pb-2 pr-4 hidden md:table-cell">Status</th>
                          <th className="text-right font-medium text-slate-400 pb-2">Score</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scans.slice(0, 5).map((s, i) => {
                          const scan = s as Record<string, unknown>;
                          const id = (scan.id as string) || String(i);
                          const filename = (scan.filename as string) || (scan.original_filename as string) || `Scan ${i + 1}`;
                          const created_at = scan.created_at as string | undefined;
                          const status = (scan.status as string) || "unknown";
                          const trust_score = (scan.trust_score as number | undefined) ?? 50;
                          return (
                            <tr key={id} className="border-b border-blue-50">
                              <td className="py-3 pr-4">
                                <div className="flex items-center gap-2">
                                  <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
                                    <Image className="w-4 h-4 text-blue-500" />
                                  </div>
                                  <span className="font-medium text-slate-700 truncate max-w-[160px]">
                                    {filename}
                                  </span>
                                </div>
                              </td>
                              <td className="py-3 pr-4 text-slate-400 hidden sm:table-cell">
                                {created_at ? new Date(created_at).toLocaleDateString() : "-"}
                              </td>
                              <td className="py-3 pr-4 hidden md:table-cell">
                                <Badge variant={status === "completed" ? "success" : status === "failed" ? "danger" : "warning"} className="rounded-md text-xs">
                                  {status}
                                </Badge>
                              </td>
                              <td className="py-3 text-right">
                                <span className={`font-bold ${trust_score >= 70 ? "text-emerald-600" : trust_score >= 40 ? "text-amber-600" : "text-rose-600"}`}>
                                  {trust_score}%
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="py-8 text-center text-slate-400">
                    <Search className="w-10 h-10 mx-auto mb-2 opacity-40" />
                    <p className="text-sm">No analyses yet</p>
                    <Link href="/analyze"><Button size="sm" className="mt-3 gap-2 rounded-xl bg-blue-600 hover:bg-blue-700"><Upload className="w-4 h-4" /> Upload First Image</Button></Link>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Incidents + Latest Report */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Recent Incidents */}
              <Card className="rounded-2xl border-blue-100 shadow-sm bg-white">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <div className="w-9 h-9 rounded-xl bg-rose-100 flex items-center justify-center">
                        <ShieldAlert className="w-5 h-5 text-rose-600" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-slate-800">Recent Incidents</h3>
                        <p className="text-xs text-slate-400">Auto-detected threats</p>
                      </div>
                    </div>
                    <Link href="/incidents">
                      <Button variant="ghost" size="sm" className="gap-1 text-xs text-blue-600">
                        View All <ArrowRight className="w-3 h-3" />
                      </Button>
                    </Link>
                  </div>
                  <div className="space-y-2">
                    {incidents.length === 0 ? (
                      <div className="py-6 text-center text-slate-400 text-sm">
                        <Shield className="w-10 h-10 mx-auto mb-2 opacity-40" />
                        <p>No incidents detected</p>
                      </div>
                    ) : (
                      incidents.slice(0, 4).map((inc, i) => {
                        const title = inc.reason || inc.title || "Security Alert";
                        const dateStr = inc.created_at ? new Date(inc.created_at).toLocaleDateString() : "";
                        const score = inc.trust_score ?? 50;
                        return (
                          <div key={inc.id || i} className="flex items-center gap-3 p-2.5 rounded-xl">
                            <div className="w-8 h-8 rounded-lg bg-rose-100 flex items-center justify-center flex-shrink-0">
                              <AlertTriangle className="w-4 h-4 text-rose-500" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-slate-700 truncate">{title}</p>
                              <p className="text-xs text-slate-400">{dateStr}</p>
                            </div>
                            <Badge className="rounded-md text-xs bg-rose-100 text-rose-700 border-rose-200">{score}%</Badge>
                          </div>
                        );
                      })
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Latest Report + Quick Actions */}
              <Card className="rounded-2xl border-blue-100 shadow-sm bg-white">
                <CardContent className="p-5">
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
                      <FileText className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-slate-800">Latest Report</h3>
                      <p className="text-xs text-slate-400">Most recent generated report</p>
                    </div>
                  </div>
                  {reports.length === 0 ? (
                    <div className="py-4 text-center text-slate-400 text-sm">
                      <FileText className="w-8 h-8 mx-auto mb-1 opacity-40" />
                      <p>No reports yet</p>
                    </div>
                  ) : (
                    <div className="p-3 rounded-xl bg-gradient-to-br from-blue-50 to-sky-50 border border-blue-100 mb-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center">
                          <FileText className="w-5 h-5 text-blue-600" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-slate-800 truncate">{reports[0].title || `Report ${reports[0].id?.slice(0, 8)}`}</p>
                          <p className="text-xs text-slate-400">
                            Trust: {reports[0].trust_score ?? "?"}% · {reports[0].created_at ? new Date(reports[0].created_at).toLocaleDateString() : ""}
                          </p>
                        </div>
                        {reports[0].pdf_url && (
                          <Button variant="ghost" size="sm" onClick={() => window.open(reports[0].pdf_url, "_blank")} className="rounded-lg">
                            <Download className="w-4 h-4 text-blue-600" />
                          </Button>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Quick Actions */}
                  <h4 className="text-sm font-semibold text-slate-700 mb-3 mt-2">Quick Actions</h4>
                  <div className="grid grid-cols-2 gap-2">
                    <QuickActionButton icon={Upload} label="Upload Image" href="/analyze" color="blue" />
                    <QuickActionButton icon={FileText} label="View Reports" href="/reports" color="sky" />
                    <QuickActionButton icon={ShieldAlert} label="Incidents" href="/incidents" color="rose" />
                    <QuickActionButton icon={Settings} label="Settings" href="/settings" color="slate" />
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>

        {/* ──────── BOTTOM ROW: Health, Storage, System, Insights ──────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {/* AI Runtime Health */}
          <Card className="rounded-2xl border-blue-100 shadow-sm bg-white">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-xl bg-blue-100 flex items-center justify-center">
                  <Cpu className="w-4 h-4 text-blue-600" />
                </div>
                <h3 className="font-semibold text-slate-800 text-sm">AI Runtime Health</h3>
              </div>
              <div className="space-y-2.5">
                <HealthRow label="Pipeline Status" value="Operational" icon={<CheckCircle2 className="w-4 h-4 text-emerald-500" />} />
                <HealthRow label="Model Loaded" value="Active" icon={<CheckCircle2 className="w-4 h-4 text-emerald-500" />} />
                <HealthRow label="Queue" value={`${data?.running_jobs || 0} jobs`} icon={<Clock className="w-4 h-4 text-amber-500" />} />
                <HealthRow label="Last Scan" value={scans.length ? new Date((scans[0] as Record<string, unknown>)?.created_at as string || "").toLocaleDateString() : "Never"} icon={<Activity className="w-4 h-4 text-blue-500" />} />
              </div>
            </CardContent>
          </Card>

          {/* Storage Usage */}
          <Card className="rounded-2xl border-blue-100 shadow-sm bg-white">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-xl bg-blue-100 flex items-center justify-center">
                  <HardDrive className="w-4 h-4 text-blue-600" />
                </div>
                <h3 className="font-semibold text-slate-800 text-sm">Storage Usage</h3>
              </div>
              <div className="mb-3">
                <div className="flex justify-between text-xs text-slate-500 mb-1.5">
                  <span>Report Storage</span>
                  <span>{data?.completed_reports || 0} files</span>
                </div>
                <Progress value={Math.min((data?.completed_reports ?? 0) * 5, 100)} max={100} className="h-2 rounded-full bg-blue-50" />
              </div>
              <div className="space-y-2">
                <HealthRow label="Uploads" value={`${data?.total_analyses || 0} files`} icon={<Upload className="w-3.5 h-3.5 text-blue-500" />} />
                <HealthRow label="Reports" value={`${data?.completed_reports || 0} files`} icon={<FileText className="w-3.5 h-3.5 text-blue-500" />} />
                <HealthRow label="PDFs" value={`${data?.completed_reports || 0} files`} icon={<DownloadCloud className="w-3.5 h-3.5 text-blue-500" />} />
              </div>
            </CardContent>
          </Card>

          {/* System Status */}
          <Card className="rounded-2xl border-blue-100 shadow-sm bg-white">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-xl bg-blue-100 flex items-center justify-center">
                  <Server className="w-4 h-4 text-blue-600" />
                </div>
                <h3 className="font-semibold text-slate-800 text-sm">System Status</h3>
              </div>
              <div className="space-y-2.5">
                <HealthRow label="API Server" value="Healthy" icon={<CheckCircle2 className="w-4 h-4 text-emerald-500" />} />
                <HealthRow label="Database (AWS RDS)" value="Connected" icon={<CheckCircle2 className="w-4 h-4 text-emerald-500" />} />
                <HealthRow label="Storage" value="Available" icon={<CheckCircle2 className="w-4 h-4 text-emerald-500" />} />
                <HealthRow label="Uptime" value="24/7" icon={<Activity className="w-4 h-4 text-blue-500" />} />
              </div>
            </CardContent>
          </Card>

          {/* Security Insights */}
          <Card className="rounded-2xl border-blue-100 shadow-sm bg-white">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-xl bg-blue-100 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-blue-600" />
                </div>
                <h3 className="font-semibold text-slate-800 text-sm">Security Insights</h3>
              </div>
              <div className="space-y-2.5">
                <InsightCard
                  icon={Shield}
                  title="Trust Assessment"
                  description={`Average trust score is ${avgScore}% - ${avgScore >= 60 ? "healthy" : avgScore >= 40 ? "monitor closely" : "requires immediate attention"}`}
                  color={avgScore >= 60 ? "emerald" : avgScore >= 40 ? "amber" : "rose"}
                />
                <InsightCard
                  icon={AlertTriangle}
                  title="Risk Alert"
                  description={`${data?.total_incidents || 0} incidents detected across ${data?.total_analyses || 0} analyses`}
                  color={(data?.total_incidents ?? 0) > 0 ? "rose" : "emerald"}
                />
                <InsightCard
                  icon={BarChart3}
                  title="Analysis Volume"
                  description={`${data?.completed_analyses || 0}/${data?.total_analyses || 0} analyses completed (${data?.total_analyses ? Math.round((data?.completed_analyses ?? 0) / (data?.total_analyses ?? 1) * 100) : 0}% success rate)`}
                  color="blue"
                />
              </div>
            </CardContent>
          </Card>
        </div>

      </div>
      <Footer />
    </div>
  );
}

// ──────── SubComponents ────────

function StatCard({
  icon, label, value, trend, trendLabel, gradient, delay,
}: {
  icon: React.ReactNode; label: string; value: string | number;
  trend: string; trendLabel: string; gradient: string; delay: number;
}) {
  return (
    <div
      className="rounded-2xl bg-white border border-blue-100 shadow-sm overflow-hidden"
      style={{ animation: `fade-in-up 0.5s ease-out ${delay * 0.08}s both` }}
    >
      <div className="p-4">
        <div className="flex items-start justify-between mb-3">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</span>
          <div className={`w-9 h-9 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center text-white shadow-sm`}>
            {icon}
          </div>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-2xl font-bold text-slate-900">{value}</span>
        </div>
        <div className="flex items-center gap-1 mt-1.5">
          <span className="text-xs text-slate-400">{trend}</span>
          <span className="text-[10px] text-slate-300">· {trendLabel}</span>
        </div>
      </div>
    </div>
  );
}

function AgentRow({ agent, index }: { agent: typeof AGENTS[0]; index: number }) {
  return (
    <div
      className="flex items-center gap-3 p-2.5 rounded-xl"
      style={{ animation: `fade-in-up 0.4s ease-out ${0.3 + index * 0.06}s both` }}
    >
      <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: `${agent.color}15` }}>
        <agent.icon className="w-4 h-4" style={{ color: agent.color }} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-700">{agent.name}</p>
        <p className="text-[11px] text-slate-400 truncate">{agent.desc}</p>
      </div>
      <Badge className="rounded-md text-[10px] bg-blue-50 text-blue-700 border-blue-200 font-medium px-2 py-0.5">
        Active
      </Badge>
    </div>
  );
}

function HealthRow({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-500 flex items-center gap-2">
        {icon}
        {label}
      </span>
      <span className="font-medium text-slate-700 text-xs">{value}</span>
    </div>
  );
}

function InsightCard({ icon: Icon, title, description, color }: { icon: any; title: string; description: string; color: string }) {
  const colorMap: Record<string, string> = {
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    rose: "bg-rose-50 text-rose-700 border-rose-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
  };
  return (
    <div className={`p-2.5 rounded-xl border ${colorMap[color] || colorMap.blue}`}>
      <div className="flex items-start gap-2">
        <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <div>
          <p className="text-xs font-semibold">{title}</p>
          <p className="text-[11px] opacity-80 mt-0.5">{description}</p>
        </div>
      </div>
    </div>
  );
}

function QuickActionButton({ icon: Icon, label, href, color }: { icon: any; label: string; href: string; color: string }) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-50 text-blue-700",
    sky: "bg-sky-50 text-sky-700",
    rose: "bg-rose-50 text-rose-700",
    slate: "bg-slate-100 text-slate-700",
  };
  return (
    <Link href={href}>
      <div className={`flex items-center gap-2 p-2.5 rounded-xl ${colorMap[color]}`}>
        <Icon className="w-4 h-4" />
        <span className="text-xs font-medium">{label}</span>
      </div>
    </Link>
  );
}