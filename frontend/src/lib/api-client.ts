/**
 * VisionX API Client
 * Unified API client for all backend communication
 * Updated for new backend architecture (v4.0.0)
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class APIClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
  }

  clearToken() {
    this.token = null;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    let retryCount = 0;
    const maxRetries = 1;

    while (retryCount <= maxRetries) {
      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };

        if (this.token) {
          headers["Authorization"] = `Bearer ${this.token}`;
        }

        if (options.headers) {
          const customHeaders = options.headers as Record<string, string>;
          Object.assign(headers, customHeaders);
        }

        const response = await fetch(url, {
          ...options,
          headers,
        });

        if (response.status === 401 && retryCount === 0 && this.token) {
          retryCount++;
          const refreshed = await this.refreshToken();
          if (refreshed) {
            continue;
          } else {
            this.clearToken();
            if (typeof window !== 'undefined') {
              window.location.href = "/login";
            }
            throw new Error("Session expired. Please login again.");
          }
        }

        if (!response.ok) {
          const error = await response.json().catch(() => ({ detail: "Request failed" }));
          const detail = error?.detail || error?.error?.message || error?.error?.message?.message;
          throw new Error(typeof detail === "string" ? detail : `HTTP ${response.status}`);
        }

        return response.json();
      } catch (error: any) {
        if (error.message === "Session expired. Please login again.") {
          throw error;
        }
        if (error.message === "Failed to fetch") {
          if (typeof window !== 'undefined' && !window.navigator.onLine) {
            throw new Error("No internet connection. Please check your network.");
          }
          throw new Error("Cannot connect to backend server. Please ensure the backend is running on http://localhost:8000");
        }
        if (error.message.includes("CORS")) {
          throw new Error("CORS error. Backend server may not be configured to accept requests from this origin.");
        }
        throw error;
      }
    }

    throw new Error("Request failed after retry");
  }

  private async refreshToken(): Promise<boolean> {
    try {
      const { authClient } = await import("@/lib/auth-session");

      const { data, error } = await authClient.auth.refreshSession();
      
      if (error || !data.session) {
        return false;
      }

      this.setToken(data.session.access_token);
      return true;
    } catch (error) {
      console.error("Token refresh failed:", error);
      return false;
    }
  }

  private async applySession(session?: { access_token?: string; refresh_token?: string } | null) {
    if (!session?.access_token || !session?.refresh_token) {
      return;
    }

    this.setToken(session.access_token);

    try {
      const { authClient } = await import("@/lib/auth-session");
      await authClient.auth.setSession({
        access_token: session.access_token,
        refresh_token: session.refresh_token,
      });
    } catch (error) {
      console.error("Failed to store session:", error);
    }
  }

  // ===========================================
  // AUTH
  // ===========================================
  async register(email: string, password: string, fullName: string) {
    const result = await this.request<{ success: boolean; message: string; user: any; session: any }>(
      "/api/auth/register",
      {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: fullName }),
      }
    );
    await this.applySession(result.session);
    return result;
  }

  async login(email: string, password: string) {
    const result = await this.request<{ success: boolean; message: string; user: any; session: any }>(
      "/api/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }
    );
    await this.applySession(result.session);
    return result;
  }

  async logout() {
    try {
      await this.request<{ success: boolean; message: string }>("/api/auth/logout", {
        method: "POST",
      });
    } catch (e) {
      // Ignore errors on logout
    }
  }

  async getCurrentUser() {
    return this.request<{ success: boolean; user: any }>("/api/auth/me");
  }

  async updateProfile(data: { full_name?: string; avatar_url?: string; username?: string; bio?: string }) {
    return this.request<{ success: boolean; message: string; profile: any }>(
      "/api/auth/profile",
      {
        method: "PUT",
        body: JSON.stringify(data),
      }
    );
  }

  async resetPassword(email: string) {
    return this.request<{ success: boolean; message: string }>("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }

  // ===========================================
  // DASHBOARD
  // ===========================================
  async getDashboardStats() {
    return this.request<{ success: boolean; stats: any }>("/api/v1/dashboard/");
  }

  // ===========================================
  // ANALYSIS
  // ===========================================
  async startAnalysis(data: { 
    module: string; 
    input_type?: string; 
    input_content: string; 
    source_url?: string; 
    title?: string 
  }) {
    return this.request<{ success: boolean; analysis_id: string; module: string; status: string }>(
      "/api/v1/analysis/analyze",
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    );
  }

  async uploadAndAnalyze(
    module: string,
    file: File,
    title?: string,
    source_url?: string
  ) {
    const formData = new FormData();
    formData.append("module", module);
    formData.append("file", file);
    if (title) formData.append("title", title);
    if (source_url) formData.append("source_url", source_url);

    const headers: Record<string, string> = {};
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/analysis/analyze/upload`, {
      method: "POST",
      body: formData,
      headers,
    });

    if (response.status === 401) {
      throw new Error("Session expired. Please login again.");
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(error.detail || "Upload failed");
    }

    return response.json();
  }

  async getAnalyses(params?: { limit?: number; offset?: number; module?: string; status?: string }) {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());
    if (params?.module) searchParams.set("module", params.module);
    if (params?.status) searchParams.set("status", params.status);

    const query = searchParams.toString();
    return this.request<{ success: boolean; analyses: any[]; count: number }>(
      `/api/v1/analysis/analyses${query ? `?${query}` : ""}`
    );
  }

  async getAnalysis(analysisId: string) {
    return this.request<{ success: boolean; analysis: any; evidence: any; report: any }>(
      `/api/v1/analysis/analyses/${analysisId}`
    );
  }

  async getAnalysisJob(analysisId: string) {
    return this.request<{ success: boolean; analysis: any; evidence: any; report: any }>(
      `/api/v1/analysis/analyses/${analysisId}`
    );
  }

  async getAnalysisStatus(analysisId: string) {
    return this.request<{ success: boolean; id: string; status: string; module?: string; trust_score?: number; risk_level?: string; confidence?: number; verdict?: string; created_at?: string; completed_at?: string; error_message?: string }>(
      `/api/v1/analysis/analyses/${analysisId}/status`
    );
  }

  async deleteAnalysis(analysisId: string) {
    return this.request<{ success: boolean; message: string }>(`/api/v1/analysis/analyses/${analysisId}`, {
      method: "DELETE",
    });
  }

  async cancelAnalysis(analysisId: string) {
    return this.request<{ success: boolean; message: string }>(`/api/v1/analysis/analyses/${analysisId}/cancel`, {
      method: "POST",
    });
  }

  // ===========================================
  // REPORTS
  // ===========================================
  async getReports(params?: { limit?: number; offset?: number }) {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());

    return this.request<{ success: boolean; reports: any[]; count: number }>(
      `/api/v1/reports/?${searchParams.toString()}`
    );
  }

  async getReport(reportId: string) {
    return this.request<{ success: boolean; report: any }>(`/api/v1/reports/${reportId}`);
  }

  async getReportByAnalysisId(analysisId: string) {
    return this.request<{ success: boolean; report: any }>(`/api/v1/reports/analysis/${analysisId}`);
  }

  async deleteReport(reportId: string) {
    return this.request<{ success: boolean; message: string }>(`/api/v1/reports/${reportId}`, {
      method: "DELETE",
    });
  }

  // ===========================================
  // INCIDENTS
  // ===========================================
  async getIncidents(params?: { status?: string; limit?: number; offset?: number }) {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());

    return this.request<{ success: boolean; incidents: any[]; count?: number }>(
      `/api/v1/incidents/?${searchParams.toString()}`
    );
  }

  async getIncident(incidentId: string) {
    return this.request<{ success: boolean; incident: any }>(`/api/v1/incidents/${incidentId}`);
  }

  async deleteIncident(incidentId: string) {
    return this.request<{ success: boolean; message: string }>(`/api/v1/incidents/${incidentId}`, {
      method: "DELETE",
    });
  }

  // ===========================================
  // NEWS VERIFICATION
  // ===========================================
  async analyzeNews(data: {
    input_type: "url" | "article" | "screenshot" | "headline";
    input_content: string;
    title?: string;
    source_url?: string;
    file?: File;
  }) {
    const formData = new FormData();
    formData.append("input_type", data.input_type);
    formData.append("input_content", data.input_content);
    if (data.title) formData.append("title", data.title);
    if (data.source_url) formData.append("source_url", data.source_url);
    if (data.file) formData.append("file", data.file);

    const headers: Record<string, string> = {};
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/news/analyze`, {
      method: "POST",
      body: formData,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Analysis failed" }));
      throw new Error(error.detail || "Analysis failed");
    }

    return response.json();
  }

  async getNewsAnalyses(params?: { limit?: number; offset?: number; status?: string }) {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());
    if (params?.status) searchParams.set("status", params.status);

    return this.request<{ success: boolean; analyses: any[]; count: number }>(
      `/api/v1/news/analysis?${searchParams.toString()}`
    );
  }

  async getNewsAnalysis(analysisId: string) {
    return this.request<{ success: boolean; analysis: any; agent_results?: any[]; sources?: any[]; claims?: any[]; report?: any }>(
      `/api/v1/news/analysis/${analysisId}`
    );
  }

  async deleteNewsAnalysis(analysisId: string) {
    return this.request<{ success: boolean; message: string }>(`/api/v1/news/analysis/${analysisId}`, {
      method: "DELETE",
    });
  }

  async getNewsAnalysisStatus(analysisId: string) {
    return this.request<{ success: boolean; status: string; authenticity_score?: number; risk_level?: string; confidence?: number; verdict?: string; agent_statuses: any; completed_at?: string; error_message?: string }>(
      `/api/v1/news/analysis/${analysisId}/status`
    );
  }

  async getNewsReports(params?: { limit?: number; offset?: number }) {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());

    return this.request<{ success: boolean; reports: any[]; count: number }>(
      `/api/v1/news/reports?${searchParams.toString()}`
    );
  }

  async getNewsReport(analysisId: string) {
    return this.request<{ success: boolean; report: any }>(`/api/v1/news/reports/${analysisId}`);
  }

  async getNewsDashboard() {
    return this.request<{ success: boolean; stats: any }>("/api/v1/news/dashboard");
  }

  // ===========================================
  // VIDEO VERIFICATION
  // ===========================================
  async getVideoAnalyses(params?: { limit?: number; offset?: number; status?: string }) {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());
    if (params?.status) searchParams.set("status", params.status);

    return this.request<{ success: boolean; analyses: any[]; count: number }>(
      `/video/history?${searchParams.toString()}`
    );
  }

  async getVideoAnalysis(analysisId: string) {
    return this.request<{ success: boolean; analysis: any; frames: any[]; evidence: any[]; audio: any; agent_results: any[]; report: any }>(
      `/video/analysis/${analysisId}`
    );
  }

  async deleteVideoAnalysis(analysisId: string) {
    return this.request<{ success: boolean; message: string }>(`/video/analysis/${analysisId}`, {
      method: "DELETE",
    });
  }

  async getVideoReports(params?: { limit?: number; offset?: number }) {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());

    return this.request<{ success: boolean; reports: any[]; count: number }>(
      `/video/reports?${searchParams.toString()}`
    );
  }

  async getVideoReport(analysisId: string) {
    return this.request<{ success: boolean; report: any }>(`/video/report/${analysisId}`);
  }

  async getVideoDashboard() {
    return this.request<{ success: boolean; stats: any }>("/video/dashboard");
  }

  // ===========================================
  // AI RUNTIME / HEALTH
  // ===========================================
  async getAIModels() {
    return { models: [] };
  }

  async getAIRuntimeHealth() {
    const health = await this.request<{ status: string; components?: Record<string, any> }>("/health");
    return {
      health: Object.entries(health.components || {}).map(([name, value]) => ({
        model_id: name,
        ...(value as Record<string, any>),
      })),
    };
  }

  async getAIRuntimeMetrics() {
    return { instances: [] };
  }

  // ===========================================
  // UPLOADS
  // ===========================================
  async getUploads(params?: { limit?: number; offset?: number; search?: string }) {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset) searchParams.set("offset", params.offset.toString());
    if (params?.search) searchParams.set("search", params.search);

    return this.request<{ success: boolean; uploads: any[]; count: number }>(
      `/api/v1/uploads/?${searchParams.toString()}`
    );
  }

  async deleteUpload(uploadId: string) {
    return this.request<{ success: boolean; message: string }>(`/api/v1/uploads/${uploadId}`, {
      method: "DELETE",
    });
  }

  async downloadReport(reportId: string, format: "json" | "pdf") {
    const response = await fetch(`${API_BASE_URL}/api/v1/reports/${reportId}/download?format=${format}`, {
      headers: {
        "Authorization": `Bearer ${this.token}`,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Download failed" }));
      throw new Error(error.detail || "Download failed");
    }

    return response.blob();
  }

  async reanalyze(uploadId: string) {
    return this.request<{ success: boolean; message: string; analysis_id: string }>(
      `/api/v1/uploads/${uploadId}/reanalyze`,
      { method: "POST" }
    );
  }

  // ===========================================
  // SSE STREAMING
  // ===========================================
  createEventSource(analysisId: string): EventSource {
    // Note: EventSource doesn't support custom headers
    // Token is passed via query parameter instead
    const token = this.token;
    const url = `${API_BASE_URL}/api/v1/analysis/analyses/${analysisId}/events${token ? `?token=${token}` : ''}`;
    return new EventSource(url);
  }
}

// Export singleton instance
export const apiClient = new APIClient();
