standingsApp.service('ErrorMessageService',  function($interval){
    var svc = {}
    svc.messages = []
    svc.timeout = 5; // Seconds
    svc.add = function(message){
        svc.messages.push(message)

        $interval(function(){
            // Remove the given message after timeout
            angular.forEach(svc.messages, function(value, key) {
                if (value === message) {
                    svc.messages.splice(key, 1)
                }
            });
        }, svc.timeout * 1000, 1);
    };

    svc.error = function (response) {
        // Error handler for angular http.METHOD
        if (response.data.Message !== undefined) {
            svc.add(response.data.Message);
        } else if (response.status == 404) {
            svc.add("Not found");
        } else if (response.status == 403) {
            svc.add("Forbidden");
        } else if (response.status == 500) {
            svc.add("Internal Server Error");
        } else {
            svc.add("An unknown error occurred attempting to process your request.");
        }
    };

    return svc;
});

angular.module('standingsApp')
    .component('errorMessages', {
    templateUrl: urls.error_template,
    controller: function ($scope, ErrorMessageService) {
        this.$onInit = function(){
            $scope.messages = ErrorMessageService.messages;
        }
    }
});
