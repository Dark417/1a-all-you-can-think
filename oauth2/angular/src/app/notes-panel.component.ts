import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { AuthService } from './auth.service';
import type { Note } from './models';
import { NotesService } from './notes.service';

@Component({
  selector: 'app-notes-panel',
  standalone: true,
  imports: [FormsModule, DatePipe],
  template: `
    <section class="card">
      <div class="card-head">
        <h2>Notes</h2>
        <button class="ghost" (click)="load()">Reload</button>
      </div>

      @if (error(); as message) {
        <p class="error">{{ message }}</p>
      }

      <form class="new-note" (ngSubmit)="add()">
        <input [(ngModel)]="title" name="title" placeholder="Title" aria-label="Title" />
        <input [(ngModel)]="body" name="body" placeholder="Body" aria-label="Body" />
        <button type="submit" class="primary">Add</button>
      </form>

      @if (loading()) {
        <p class="muted">Loading…</p>
      } @else {
        <ul class="notes">
          @for (note of notes(); track note.id) {
            <li>
              <div>
                <strong>{{ note.title }}</strong>
                <p>{{ note.body }}</p>
                <span class="muted">
                  {{ note.ownerName }}@if (mine(note)) { (you) } · {{ note.createdAt | date: 'shortDate' }}
                </span>
              </div>
              <button
                class="danger"
                [disabled]="!mine(note) && !canDeleteAny()"
                [title]="!mine(note) && !canDeleteAny() ? 'Only the owner or an admin can delete this' : 'Delete'"
                (click)="remove(note.id)"
              >
                Delete
              </button>
            </li>
          }
        </ul>
      }

      <p class="muted small">
        Deleting someone else's note requires the <code>admin</code> group. Sign in as <code>bob</code> to see the
        button disabled — and note that the API rejects it too, the UI is only being polite.
      </p>
    </section>
  `,
})
export class NotesPanelComponent {
  private readonly notesService = inject(NotesService);
  private readonly auth = inject(AuthService);

  readonly notes = signal<Note[]>([]);
  readonly canDeleteAny = signal(false);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  title = '';
  body = '';

  constructor() {
    void this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const data = await firstValueFrom(this.notesService.list());
      this.notes.set(data.notes);
      this.canDeleteAny.set(data.permissions.canDeleteAny);
      this.error.set(null);
    } catch (err) {
      this.error.set(describe(err));
    } finally {
      this.loading.set(false);
    }
  }

  async add(): Promise<void> {
    if (!this.title.trim()) return;
    try {
      await firstValueFrom(this.notesService.create(this.title, this.body));
      this.title = '';
      this.body = '';
      await this.load();
    } catch (err) {
      this.error.set(describe(err));
    }
  }

  async remove(id: string): Promise<void> {
    try {
      await firstValueFrom(this.notesService.remove(id));
      await this.load();
    } catch (err) {
      this.error.set(describe(err));
    }
  }

  mine(note: Note): boolean {
    return note.ownerSub === this.auth.user()?.sub;
  }
}

function describe(err: unknown): string {
  if (err instanceof HttpErrorResponse) return err.error?.message ?? err.message;
  return String(err);
}
