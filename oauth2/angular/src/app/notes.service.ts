import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { environment } from '../environment';
import type { Note, NotesResponse } from './models';

@Injectable({ providedIn: 'root' })
export class NotesService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiBaseUrl}/api/notes`;

  list() {
    return this.http.get<NotesResponse>(this.base);
  }

  create(title: string, body: string) {
    return this.http.post<{ note: Note }>(this.base, { title, body });
  }

  remove(id: string) {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
