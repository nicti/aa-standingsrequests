standingsApp.controller('PilotListController', function ($scope, $http) {
    $scope.getData = function () {
        $http.get(urls.pilots_json).then(function(response) {
            // Success
            document.getElementById("tr_spinner").style.display = 'none';
            $scope.pilots = response.data;
        }, function(response) {
            // Unsuccessful
        });
    };

    $scope.currentPage = 1;
    $scope.pageSize = '50';
    $scope.getData();
});
