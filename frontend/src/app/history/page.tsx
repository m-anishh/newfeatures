"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/layout/navbar";
import { Footer } from "@/components/layout/footer";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/auth-context";
import { useAnalyses } from "@/hooks/use-unified-data";
import { ModuleBadge, ModuleIcon } from "@/components/analysis/shared/module-badge";
import { Trash2, ExternalLink, Loader2, Search, Download } from "lucide-react";
import { unifiedApi } from "@/lib/unified-api";

const MODULES = ["all", "image", "news", "video"] as const;

export default function UnifiedHistoryPage() {
  const { user } = useAuth();
  const [module, setModule] = useState<string>("all");
  const [search, setSearch] = useState("");
  const { data: analyses, count, loading, error, refresh } = useAnalyses(module, { limit: 50 });

  const handleDelete = async (m: string, id: string) => {
    if (!confirm("Are you sure you want to delete this analysis?")) return;
    try {
      await unifiedApi.deleteAnalysis(m, id);
      refresh();
    } catch (err: any) {
      alert(err.message || "Failed to delete");
    }
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-12"><p className="text-muted">Please log in to view history.</p></div>
        </div>
      </div>
    );
  }

  const filtered = search
    ? analyses.filter((a: any) =>
        (a.title || a.input_content || "").toLowerCase().includes(search.toLowerCase())
      )
    : analyses;

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-text mb-2">Analysis History</h1>
          <p className="text-sm text-muted">{count} total analyses across all modules</p>
        </div>

        {/* Module Filter Tabs */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {MODULES.map((m) => (
            <Button
              key={m}
              variant={module === m ? "primary" : "ghost"}
              size="sm"
              onClick={() => setModule(m)}
              className="gap-2 capitalize"
            >
              {m !== "all" && <ModuleIcon module={m} className="w-4 h-4" />}
              {m === "all" ? "All" : m}
            </Button>
          ))}
          <div className="ml-auto relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-4 py-2 rounded-xl border border-border bg-surface text-sm w-48"
            />
          </div>
        </div>

        {error && <Alert variant="error" title="Error" className="mb-6">{error}</Alert>}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-12 h-12 animate-spin text-primary" />
          </div>
        ) : filtered.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <Search className="w-16 h-16 text-slate-300 mx-auto mb-4" />
              <h3 className="text-xl font-semibold text-text mb-2">No History Yet</h3>
              <p className="text-muted mb-6">Start analyzing content to see your history here</p>
              <Link href="/analyze"><Button>Start New Analysis</Button></Link>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {filtered.map((analysis: any) => {
              const m = analysis.module || "image";
              const analysisId = analysis.id || analysis.analysis_id;
              const detailPath = m === "video" ? `/news/video/${analysisId}` : `/news/analyze/${analysisId}`;
              return (
                <Card key={analysisId} className="hover:shadow-md transition-shadow">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <ModuleBadge module={m} />
                          <h3 className="text-lg font-semibold text-text truncate">
                            {analysis.title || analysis.input_content?.slice(0, 100) || "Analysis"}
                          </h3>
                          <Badge variant={analysis.status === "completed" ? "success" : analysis.status === "failed" ? "danger" : "warning"}>
                            {analysis.status}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-4 text-sm text-muted flex-wrap">
                          <span>{new Date(analysis.created_at).toLocaleDateString()}</span>
                          {analysis.trust_score && (
                            <><span>•</span><span className="font-medium text-text">{Math.round(analysis.trust_score)}% trust</span></>
                          )}
                          {analysis.confidence && (
                            <><span>•</span><span className="font-medium text-text">{Math.round(analysis.confidence * 100)}% confidence</span></>
                          )}
                          {analysis.processing_time_ms && (
                            <><span>•</span><span>{Math.round(analysis.processing_time_ms / 1000)}s</span></>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Link href={detailPath}>
                          <Button variant="ghost" size="sm" className="gap-1">
                            <ExternalLink className="w-4 h-4" /> View
                          </Button>
                        </Link>
                        <Button variant="ghost" size="sm" onClick={() => handleDelete(m, analysisId)} className="text-red-600 hover:text-red-700">
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
      <Footer />
    </div>
  );
}