'use strict';

angular.module('xos.sampleView', [
  'ngResource',
  'ngCookies',
  'ui.router',
  'xos.helpers'
])
.config(($stateProvider) => {
  $stateProvider
  .state('user-list', {
    url: '/',
    template: '<users-list></users-list>'
  });
})
.config(function($httpProvider){
  $httpProvider.interceptors.push('NoHyperlinks');
})
.directive('usersList', function(){
  return {
    restrict: 'E',
    scope: {},
    bindToController: true,
    controllerAs: 'vm',
    templateUrl: 'templates/users-list.tpl.html',
    controller: function(Users){

      this.tableConfig = {
        columns: [
          {
            label: 'E-Mail',
            prop: 'email'
          },
          {
            label: 'First Name',
            prop: 'firstname'
          },
          {
            label: 'Last Name',
            prop: 'lastname'
          }
        ],
        classes: 'table table-striped table-condensed',
        actions: [
          {
            label: 'delete',
            icon: 'remove',
            cb: (user) => {
              console.log(user);
            },
            color: 'red'
          }
        ],
        filter: 'field',
        order: true,
        pagination: {
          pageSize: 3
        }
      };

      this.alertConfig = {
        type: 'danger',
        closeBtn: true
      }

      this.formConfig = {
        exclude: ['password'],
        formName: 'myForm',
        fields: {
        },
        actions: [
          {
            label: 'Save',
            icon: 'ok', // refers to bootstraps glyphicon
            cb: (user) => { // receive the model
              console.log(user);
            },
            class: 'success'
          }
        ]
      }

      // retrieving user list
      Users.query().$promise
      .then((users) => {
        this.users = users.concat(users).concat(users);
      })
      .catch((e) => {
        throw new Error(e);
      });
    }
  };
});