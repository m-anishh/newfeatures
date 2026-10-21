"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Navbar } from "@/components/layout/navbar";
import { Footer } from "@/components/layout/footer";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { useAuth } from "@/lib/auth-context";
import { apiClient } from "@/lib/api-client";
import { VerificationSelector, VERIFICATION_TYPES } from "@/components/analysis/verification-selector";
import { 
  Loader2, Upload, Link, FileText, Image, 
  ShieldCheck, ArrowRight, Clock
} from "lucide-react";
import ImageUploadForm from "@/components/analysis/forms/image-upload-form";
import NewsUploadForm from "@/components/analysis/forms/news-upload-form";
import VideoUploadForm from "@/components/analysis/forms/video-upload-form-real";

type InputMode = "url" | "article" | "screenshot" | "headline";

export default function UnifiedAnalyzePage() {
  const { user } = useAuth();
  const router = useRouter();
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<any>(null);

  if (!user) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-12">
            <p className="text-muted">Please log in to analyze content.</p>
          </div>
        </div>
      </div>
    );
  }

  const handleVerificationComplete = (data: any) => {
    setResult(data);
    
    // Redirect to appropriate analysis page
    if (data.analysis_id || data.image_analysis_id || data.news_analysis_id || data.analysisId) {
      const analysisId = data.analysis_id || data.image_analysis_id || data.news_analysis_id || data.analysisId;
      const path = selectedType === "news" ? `/news/analyze/${analysisId}` : `/analyze/${analysisId}`;
      setTimeout(() => {
        router.push(path);
      }, 1500);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-text mb-2">
            Start New Verification
          </h1>
          <p className="text-muted">
            Choose what you want VisionX to verify.
          </p>
        </div>

        {error && (
          <Alert variant="error" title="Error" className="mb-6">
            {error}
          </Alert>
        )}

        {result && (
          <Alert variant="success" title="Analysis Started" className="mb-6">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5" />
              <span>Analysis started successfully. Redirecting...</span>
            </div>
          </Alert>
        )}

        {!selectedType ? (
          /* Verification Type Selector */
          <div>
            <VerificationSelector 
              selectedType={selectedType} 
              onSelect={setSelectedType} 
            />
          </div>
        ) : (
          /* Dynamic Upload Form */
          <div className="space-y-6">
            {/* Back Button */}
            <Button
              variant="ghost"
              onClick={() => {
                setSelectedType(null);
                setError("");
                setResult(null);
              }}
              className="gap-2"
            >
              <ArrowRight className="w-4 h-4 rotate-180" />
              Back to selection
            </Button>

            {/* Selected Type Header */}
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center gap-3">
                  <div className={`
                    w-12 h-12 rounded-xl bg-gradient-to-br 
                    ${VERIFICATION_TYPES.find(t => t.id === selectedType)?.gradient}
                    flex items-center justify-center text-white shadow-lg
                  `}>
                    {VERIFICATION_TYPES.find(t => t.id === selectedType)?.icon}
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-text">
                      {VERIFICATION_TYPES.find(t => t.id === selectedType)?.title}
                    </h2>
                    <p className="text-sm text-muted">
                      {VERIFICATION_TYPES.find(t => t.id === selectedType)?.description}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Dynamic Form */}
            {selectedType === "image" && (
              <ImageUploadForm
                onComplete={handleVerificationComplete}
                onError={setError}
              />
            )}

            {selectedType === "news" && (
              <NewsUploadForm
                onComplete={handleVerificationComplete}
                onError={setError}
              />
            )}

            {selectedType === "video" && (
              <VideoUploadForm
                onComplete={handleVerificationComplete}
                onError={setError}
              />
            )}

            {selectedType === "document" && (
              <ComingSoonPlaceholder
                title="Document Verification"
                description="Upload PDFs, Word documents, and other file types for authenticity verification."
              />
            )}

            {selectedType === "audio" && (
              <ComingSoonPlaceholder
                title="Audio Verification"
                description="Upload audio files to detect AI-generated content and voice cloning."
              />
            )}
          </div>
        )}
      </div>

      <Footer />
    </div>
  );
}

function ComingSoonPlaceholder({ title, description }: { title: string; description: string }) {
  return (
    <Card>
      <CardContent className="p-12 text-center">
        <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-slate-400 to-slate-500 flex items-center justify-center text-white mx-auto mb-6 shadow-xl">
          <ShieldCheck className="w-10 h-10" />
        </div>
        <h3 className="text-2xl font-bold text-text mb-3">{title}</h3>
        <p className="text-muted mb-6 max-w-md mx-auto">{description}</p>
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-100 text-slate-600">
          <Clock className="w-4 h-4" />
          <span className="text-sm font-medium">Coming Soon</span>
        </div>
      </CardContent>
    </Card>
  );
}