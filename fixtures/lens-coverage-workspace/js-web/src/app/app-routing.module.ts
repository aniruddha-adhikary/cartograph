import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { BookComponent } from './book.component';

const routes: Routes = [
    { path: 'books', component: BookComponent },
    { path: 'books/new', component: BookComponent },
];

@NgModule({
    imports: [RouterModule.forRoot(routes)],
})
export class AppRoutingModule {}
