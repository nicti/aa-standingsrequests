angular.module('standingsApp')
    .controller('ViewRequestsController', ['$scope', 'viewRequestsDataFactory', 'requestsDataFactory', 'ErrorMessageService',
    function ($scope, viewRequestsDataFactory, requestsDataFactory, ErrorMessageService) {

    getRequestData();

    function getRequestData() {        
        viewRequestsDataFactory.getRequests().then(function(response) {            
            // Success
            document.getElementById("div_spinner").style.display = 'none';
            document.getElementById("div_requests").style.visibility = 'visible';
            $scope.requests = response.data;
        }, ErrorMessageService.error);
    }

    function spliceRequestContact (contact) {
        $scope.requests.splice($scope.requests.indexOf(contact), 1);
    }

    $scope.rejectRequest = function (contact) {
        requestsDataFactory.deleteRequest(contact.contact_id).then(function(response) {
            // Success
            spliceRequestContact(contact);
        }, ErrorMessageService.error)
    };
}]);

angular.module('standingsApp')
    .factory('viewRequestsDataFactory', ['$http', function($http) {

    var urlBase = urls.view_requests_json_base;
    var fac = {};

    fac.getRequests = function () {
        return $http.get(urlBase);
    };

    return fac;
}]);
