"use client";

import React, { useState, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Upload,
  Video,
  Film,
  ShieldCheck,
  CloudUpload,
  X,
  Loader2,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";

interface VideoUploadFormProps {
  onComplete?: (data: any) => void;
  onError?: (error: string) => void;
}

export default function VideoUploadForm({ onComplete, onError }: VideoUploadFormProps) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const { session } = useAuth();

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  }, []);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  }, []);

  const handleFile = async (file: File) => {
    setUploading(true);
    setProgress(0);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("input_type", "upload");
      formData.append("input_content", file.name);
      formData.append("title", file.name);

      console.log("[VideoUploadForm] Uploading file:", file.name, "size:", file.size, "type:", file.type);
      for (const [key, value] of formData.entries()) {
        console.log("[VideoUploadForm] FormData field:", key, "value:", value);
      }

      // Simulate progress
      const progressInterval = setInterval(() => {
        setProgress(prev => Math.min(prev + 10, 90));
      }, 500);

      const headers: Record<string, string> = {};
      const token = session?.access_token;
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
        console.log("[VideoUploadForm] Using token:", token.slice(0, 20) + "...");
      } else {
        console.warn("[VideoUploadForm] No token available");
      }

      const response = await fetch("/api/video/upload", {
        method: "POST",
        body: formData,
        headers,
      });

      console.log("[VideoUploadForm] Response status:", response.status);

      clearInterval(progressInterval);
      setProgress(100);

      if (!response.ok) {
        throw new Error("Upload failed");
      }

      const result = await response.json();
      console.log("Upload successful:", result);
      
      // Redirect to analysis page
      setTimeout(() => {
        window.location.href = `/news/video/${result.analysis_id}`;
      }, 1000);
    } catch (error) {
      console.error("Upload error:", error);
      setUploading(false);
      setProgress(0);
    }
  };

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
              description="AI-powered analysis"
            />
          </div>
        </div>

        <div className="px-5 py-6 sm:px-7">
          <div
            className={`flex min-h-[280px] flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
              dragActive
                ? "border-primary bg-primary/5"
                : "border-primary/50 bg-background"
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-full border border-border bg-surface text-primary">
              {uploading ? (
                <Loader2 className="h-10 w-10 animate-spin" />
              ) : (
                <CloudUpload className="h-10 w-10" />
              )}
            </div>

            <h4 className="text-lg font-bold text-text">
              {uploading ? "Uploading..." : "Upload video for analysis"}
            </h4>

            <p className="mt-2 max-w-md text-sm leading-6 text-muted">
              {uploading
                ? "Please wait while we process your video..."
                : "Drag and drop your video here, or click to browse. Supports MP4, WEBM, MOV up to 500MB."}
            </p>

            {uploading && (
              <div className="mt-6 w-full max-w-md">
                <Progress value={progress} className="h-2" />
                <p className="mt-2 text-sm text-muted">{progress}%</p>
              </div>
            )}

            {!uploading && (
              <div className="mt-6">
                <input
                  type="file"
                  id="video-upload"
                  className="hidden"
                  accept="video/mp4,video/webm,video/mov"
                  onChange={handleChange}
                />
                <label htmlFor="video-upload" className="cursor-pointer">
                  <Button type="button" className="pointer-events-none">
                    <Upload className="h-4 w-4" />
                    Select Video
                  </Button>
                </label>
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-4 border-t border-border px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <p className="text-xs text-muted">
            Current release focuses on image and document evidence analysis.
          </p>
          <Button type="button" disabled={uploading}>
            {uploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {uploading ? "Processing..." : "Upload Video"}
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