/**
 * API client for clustering operations.
 */

import apiClient from './client';

// Types
export interface ClusteringConfiguration {
  id: string;
  name: string;
  description?: string;
  algorithm: 'hdbscan' | 'kmeans' | 'dbscan' | 'agglomerative';
  min_cluster_size: number;
  min_samples: number;
  cluster_selection_method: 'eom' | 'leaf';
  cluster_selection_epsilon: number;
  metric: 'euclidean' | 'cosine' | 'manhattan' | 'l2';
  n_jobs: number;
  auto_optimize: boolean;
  optimization_metric?: string;
  created_at: string;
  updated_at: string;
}

export interface ClusterMember {
  id: string;
  sample_id: string;
  sample_type: string;
  membership_probability: number;
  distance_to_centroid: number;
  outlier_score: number;
  sample_metadata: Record<string, any>;
}

export interface Cluster {
  id: string;
  cluster_id: number;
  label?: string;
  description?: string;
  size: number;
  centroid: number[];
  radius: number;
  density: number;
  cohesion: number;
  separation: number;
  stability: number;
  representative_sample_ids: string[];
  common_patterns?: string[];
  is_outlier: boolean;
  member_count: number;
  members?: ClusterMember[];
  // 2D projection coordinates
  x?: number;
  y?: number;
}

export interface ClusteringRun {
  id: string;
  configuration: string | ClusteringConfiguration;
  evaluation_run_id?: string;
  dataset_version_id?: string;
  name?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  n_clusters: number;
  n_outliers: number;
  silhouette_score?: number;
  calinski_harabasz_score?: number;
  davies_bouldin_score?: number;
  embedding_model?: string;
  embedding_cache_hits: number;
  embedding_cache_misses: number;
  processing_time_seconds?: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface ClusteringSummaryStats {
  total_samples: number;
  n_clusters: number;
  n_outliers: number;
  avg_cluster_size: number;
  min_cluster_size: number;
  max_cluster_size: number;
  silhouette_score?: number;
  coverage_ratio: number;
}

export interface ClusterAction {
  id: string;
  cluster_id: string;
  action_type: 'retrain' | 'investigate' | 'ignore' | 'fix' | 'custom';
  description: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  assigned_to?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled';
  created_at: string;
  updated_at: string;
}

// API Methods
export const clusteringApi = {
  // Configurations
  getConfigurations: async () => {
    const response = await apiClient.get<ClusteringConfiguration[]>('/clustering-configs/');
    return response.data;
  },

  getConfiguration: async (id: string) => {
    const response = await apiClient.get<ClusteringConfiguration>(`/clustering-configs/${id}/`);
    return response.data;
  },

  createConfiguration: async (config: Partial<ClusteringConfiguration>) => {
    const response = await apiClient.post<ClusteringConfiguration>('/clustering-configs/', config);
    return response.data;
  },

  updateConfiguration: async (id: string, config: Partial<ClusteringConfiguration>) => {
    const response = await apiClient.patch<ClusteringConfiguration>(`/clustering-configs/${id}/`, config);
    return response.data;
  },

  deleteConfiguration: async (id: string) => {
    await apiClient.delete(`/clustering-configs/${id}/`);
  },

  // Clustering Runs
  getRuns: async (params?: { evaluation_run_id?: string; dataset_version_id?: string; status?: string }) => {
    const response = await apiClient.get<ClusteringRun[]>('/clustering-runs/', { params });
    return response.data;
  },

  getRun: async (id: string) => {
    const response = await apiClient.get<ClusteringRun>(`/clustering-runs/${id}/`);
    return response.data;
  },

  createRun: async (data: { configuration_id: string; evaluation_run_id?: string; dataset_version_id?: string; name?: string }) => {
    const response = await apiClient.post<ClusteringRun>('/clustering-runs/', data);
    return response.data;
  },

  cancelRun: async (id: string) => {
    const response = await apiClient.post(`/clustering-runs/${id}/cancel/`);
    return response.data;
  },

  // Clusters
  getClusters: async (runId: string) => {
    const response = await apiClient.get<Cluster[]>(`/clustering-runs/${runId}/clusters/`);
    return response.data;
  },

  getCluster: async (runId: string, clusterId: string) => {
    const response = await apiClient.get<Cluster>(`/clustering-runs/${runId}/clusters/${clusterId}/`);
    return response.data;
  },

  updateClusterLabel: async (runId: string, clusterId: string, label: string, description?: string) => {
    const response = await apiClient.patch<Cluster>(`/clustering-runs/${runId}/clusters/${clusterId}/update-label/`, {
      label,
      description
    });
    return response.data;
  },

  // Cluster Members
  getClusterMembers: async (runId: string, clusterId: string, limit = 100, offset = 0) => {
    const response = await apiClient.get<{ results: ClusterMember[]; count: number }>(
      `/clustering-runs/${runId}/clusters/${clusterId}/members/`,
      { params: { limit, offset } }
    );
    return response.data;
  },

  // Summary and Statistics
  getRunSummary: async (runId: string) => {
    const response = await apiClient.get<ClusteringSummaryStats>(`/clustering-runs/${runId}/summary/`);
    return response.data;
  },

  // Similar Samples
  findSimilarSamples: async (runId: string, sampleId: string, k = 10) => {
    const response = await apiClient.post<{ samples: ClusterMember[]; cluster_id: number }>(
      `/clustering-runs/${runId}/similar-samples/`,
      { sample_id: sampleId, k }
    );
    return response.data;
  },

  // Visualization Data
  getVisualizationData: async (runId: string) => {
    const response = await apiClient.get<{
      clusters: Array<Cluster & { x: number; y: number }>;
      projection_method: string;
      explained_variance?: number;
    }>(`/clustering-runs/${runId}/visualization/`);
    return response.data;
  },

  // Cluster Actions
  getClusterActions: async (clusterId: string) => {
    const response = await apiClient.get<ClusterAction[]>(`/clusters/${clusterId}/actions/`);
    return response.data;
  },

  createClusterAction: async (clusterId: string, action: Partial<ClusterAction>) => {
    const response = await apiClient.post<ClusterAction>(`/clusters/${clusterId}/actions/`, action);
    return response.data;
  },

  updateClusterAction: async (clusterId: string, actionId: string, update: Partial<ClusterAction>) => {
    const response = await apiClient.patch<ClusterAction>(`/clusters/${clusterId}/actions/${actionId}/`, update);
    return response.data;
  },

  deleteClusterAction: async (clusterId: string, actionId: string) => {
    await apiClient.delete(`/clusters/${clusterId}/actions/${actionId}/`);
  },
};