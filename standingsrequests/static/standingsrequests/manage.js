angular.module('standingsApp')
    .controller('ManageStandingsController', ['$scope', 'requestsDataFactory', 'revocationsDataFactory', 'ErrorMessageService',
        function ($scope, requestsDataFactory, revocationsDataFactory, ErrorMessageService) {

            getRequestData();
            getRevocationData();

            function getRequestData() {
                requestsDataFactory.getRequests().then(function (response) {
                    // Success            
                    document.getElementById("div_spinner_requests").style.display = 'none';
                    document.getElementById("div_requests").style.visibility = 'visible';
                    $scope.requests = response.data;
                }, ErrorMessageService.error);
            };

            function spliceRequestContact(contact) {
                $scope.requests.splice($scope.requests.indexOf(contact), 1);
            }

            $scope.rejectRequest = function (contact) {
                requestsDataFactory.deleteRequest(contact.contact_id).then(function (response) {
                    // Success
                    spliceRequestContact(contact);
                }, ErrorMessageService.error)
            };

            $scope.actionRequest = function (contact) {
                requestsDataFactory.actionRequest(contact.contact_id).then(function (response) {
                    // Success
                    spliceRequestContact(contact);
                }, ErrorMessageService.error)
            };

            // Revocations
            function getRevocationData() {
                revocationsDataFactory.getRevocations().then(function (response) {
                    // Success            
                    document.getElementById("div_spinner_revocations").style.display = 'none';
                    document.getElementById("div_revocations").style.visibility = 'visible';
                    $scope.revocations = response.data;
                }, ErrorMessageService.error);
            };

            function spliceRevocationContact(contact) {
                $scope.revocations.splice($scope.revocations.indexOf(contact), 1);
            }

            $scope.deleteRevocation = function (contact) {
                revocationsDataFactory.deleteRevocation(contact.contact_id).then(function (response) {
                    // Success
                    spliceRevocationContact(contact);
                }, ErrorMessageService.error)
            };

            $scope.actionRevocation = function (contact) {
                revocationsDataFactory.actionRevocation(contact.contact_id).then(function (response) {
                    // Success
                    spliceRevocationContact(contact);
                }, ErrorMessageService.error)
            };
        }]);

angular.module('standingsApp')
    .factory('requestsDataFactory', ['$http', function ($http) {

        var urlBase = urls.standings_requests_json_base;
        var fac = {};

        fac.getRequests = function () {
            return $http.get(urlBase);
        };

        fac.actionRequest = function (contact_id) {
            return $http.put(urlBase + contact_id + '/');
        };

        fac.deleteRequest = function (contact_id) {
            return $http.delete(urlBase + contact_id + '/');
        };

        return fac;
    }]);

angular.module('standingsApp')
    .factory('revocationsDataFactory', ['$http', function ($http) {

        var urlBase = urls.standings_revocations_json_base;
        var fac = {};

        fac.getRevocations = function () {
            return $http.get(urlBase);
        };

        fac.actionRevocation = function (contact_id) {
            return $http.put(urlBase + contact_id + '/');
        };

        fac.deleteRevocation = function (contact_id) {
            return $http.delete(urlBase + contact_id + '/');
        };

        return fac;
    }]);


