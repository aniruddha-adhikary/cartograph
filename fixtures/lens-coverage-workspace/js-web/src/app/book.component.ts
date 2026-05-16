import { Component, Directive, Injectable, NgModule, Pipe } from '@angular/core';

@Component({
    selector: 'app-book',
    templateUrl: './book.component.html',
})
export class BookComponent {}

@Directive({ selector: '[appHighlight]' })
export class HighlightDirective {}

@Injectable({ providedIn: 'root' })
export class BookService {}

@NgModule({
    declarations: [BookComponent],
    imports: [],
})
export class BookModule {}

@Pipe({ name: 'titleCase' })
export class TitleCasePipe {}
