import { toIsbn13 } from "./isbn";

export interface Book {
  isbn: string;
  title: string;
  copies: number;
  price: number;
}

export class Catalogue {
  private books = new Map<string, Book>();

  add(isbn: string, title: string, price: number): Book {
    const key = toIsbn13(isbn);
    const known = this.books.get(key);
    if (known) {
      known.copies += 1;
      return known;
    }
    const book = { isbn: key, title, copies: 1, price };
    this.books.set(key, book);
    return book;
  }

  find(isbn: string): Book | undefined {
    return this.books.get(toIsbn13(isbn));
  }

  search(text: string): Book[] {
    const needle = text.trim().toLowerCase();
    if (!needle) return [];
    return [...this.books.values()].filter((book) => book.title.toLowerCase().includes(needle));
  }

  remove(isbn: string, copiesOnLoan: number): void {
    if (copiesOnLoan > 0) throw new Error("a copy is on loan");
    this.books.delete(toIsbn13(isbn));
  }
}
