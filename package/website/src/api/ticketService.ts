// src/services/ticketService.ts
import request from '@/utils/request';
import type { TicketBackend, TicketQueryParams, FlightTicketBackend } from '@/types/ticket';

export const ticketService = {
  async recognizeByType(type: 'train' | 'flight', file: File) {
    const payload = new FormData(); payload.append('file', file);
    return (await request.post<Record<string, unknown>>(`/api/${type === 'train' ? 'train' : 'flight'}-ticket/recognize`, payload)).data;
  },
  async trainSchedules(code: string) {
    return (await request.get<{ list: Array<{ station_name: string; accumulated_mileage: number; running_time: number; sequence: number }> }>('/api/railway/train-schedules', { params: { train_code: code, page: 1, page_size: 100 } })).data;
  },
  // 获取列表
  async getTickets(params: TicketQueryParams) {
    const data = await request.get<{ items: TicketBackend[], total: number }>('/api/train-ticket', { params });
    return data.data;
  },

  // 创建
  async createTicket(data: Partial<TicketBackend>) {
    const res = await request.post<TicketBackend>('/api/train-ticket', data);
    return res;
  },

  // 获取飞机票列表
  async getFlightTickets(params: TicketQueryParams) {
    const data = await request.get<{ items: FlightTicketBackend[], total: number }>('/api/flight-ticket', { params });
    // 标记类型
    data.data.items.forEach(item => item.type = 'flight');
    return data.data;
  },

  // 创建飞机票
  async createFlightTicket(data: Partial<FlightTicketBackend>) {
    const res = await request.post<FlightTicketBackend>('/api/flight-ticket', data);
    res.data.type = 'flight';
    return res.data;
  },

  // 更新飞机票
  async updateFlightTicket(id: string, data: Partial<FlightTicketBackend>) {
    const res = await request.put<FlightTicketBackend>(`/api/flight-ticket/${id}`, data);
    res.data.type = 'flight';
    return res.data;
  },

  // 删除飞机票
  async deleteFlightTicket(id: string) {
    await request.delete(`/api/flight-ticket/${id}`);
    return true;
  },

  // 更新
  async updateTicket(id: number | string, data: Partial<TicketBackend>) {
    const res = await request.put<TicketBackend>(`/api/train-ticket/${id}`, data);
    res.data.type = 'train';
    return res.data;
  },

  // 删除
  async deleteTicket(id: number | string) {
    await request.delete(`/api/train-ticket/${id}`);
    return true;
  },

  // 批量删除 (前端循环调用或后端支持批量接口)
  async batchDeleteTickets(ids: (number | string)[]) {
    // 假设后端没有批量接口，使用 Promise.all
    const promises = ids.map(id => request.delete(`/api/train-ticket/${id}`));
    await Promise.all(promises);
    return true;
  },

  // 识别车票
  async recognizeTicket(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    const data = await request.post('/api/train-ticket/recognize', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    return data.data;
  },

  // 导出数据
  async exportTickets(format: 'json' | 'csv' = 'json') {
    const response = await request.get(`/api/train-ticket/export`, {
      params: { format },
      responseType: 'blob'
    });
    // response is the blob data directly because of request interceptor logic on 'blob'
    
    // 创建下载链接
// src/services/ticketService.ts
    const url = window.URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `tickets_export_${new Date().getTime()}.${format}`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  },

  // 导入数据
  async importTickets(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await request.post('/api/train-ticket/import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    return data;
  }
};

