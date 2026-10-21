"use client";

import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Upload,
  Clock,
  Video,
  Film,
  ShieldCheck,
  CloudUpload,
  X,
} from "lucide-react";

export default function VideoUploadForm() {
  return (
    <Card className="overflow-hidden border-border bg-surface">
      <CardContent className="p-0">
        <div className="border-b border-border px-5 py-5 sm:px-7">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-xl font-bold text-text">Upload video</h3>
              <p className="mt-1 text-sm text-muted">
                Video authenticity verification module.
              </p>
            </div>

            <div className="hidden h-9 w-9 items-center justify-center rounded-full border border-border text-muted sm:flex">
              <X className="h-4 w-4" />
            </div>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <VideoInfo
              icon={<Video className="h-5 w-5" />}
              title="Videos"
              description="MP4, WEBM, MOV"
            />

            <VideoInfo
              icon={<Film className="h-5 w-5" />}
              title="Frames"
              description="Deepfake frame checks"
            />

            <VideoInfo
              icon={<ShieldCheck className="h-5 w-5" />}
              title="Trust report"
              description="Coming in future"
            />
          </div>
        </div>

        <div className="px-5 py-6 sm:px-7">
          <div className="flex min-h-[280px] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-primary/50 bg-background px-6 py-10 text-center">
            <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-full border border-border bg-surface text-primary">
              <CloudUpload className="h-10 w-10" />
            </div>

            <h4 className="text-lg font-bold text-text">
              Video verification is coming soon
            </h4>

            <p className="mt-2 max-w-md text-sm leading-6 text-muted">
              This module will support video upload, frame-level authenticity
              checks, deepfake detection, and explainable video trust reports.
            </p>

            <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-4 py-2 text-primary">
              <Clock className="h-4 w-4" />
              <span className="text-sm font-medium">Coming Soon</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4 border-t border-border px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <p className="text-xs text-muted">
            Current release focuses on image and document evidence analysis.
          </p>

          <Button type="button" disabled className="min-w-[160px]">
            <Upload className="h-4 w-4" />
            Upload Video
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function VideoInfo({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-border bg-background p-4">
      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        {icon}
      </div>

      <div>
        <p className="text-sm font-semibold text-text">{title}</p>
        <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
      </div>
    </div>
  );
}
